import os
import html
import uuid
import asyncio

import urllib.parse
import datetime

from typing import List

import yaml

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# pylint: disable=no-name-in-module
from pydantic import BaseModel

from managers import K8SManager, StorageManager


# ============================================================================
class CaptureRequest(BaseModel):
    # pylint: disable=too-few-public-methods
    urls: List[str]
    userid: str = "user"
    tag: str = ""
    embeds: bool = False


# ============================================================================
class MainController:
    # pylint: disable=too-many-instance-attributes
    def __init__(self):
        self.app = FastAPI()

        self.app.mount("/static", StaticFiles(directory="static"), name="static")
        self.app.mount("/replay", StaticFiles(directory="replay"), name="replay")

        self.templates = Jinja2Templates(directory="templates")

        self.storage = StorageManager()
        self.k8s = K8SManager()

        self.profile_url = os.environ.get("PROFILE_URL", "")
        self.headless = os.environ.get("HEADLESS", "") == "1" and not self.profile_url

        self.use_vnc = os.environ.get("VNC") == "1" and not self.headless

        self.access_prefix = os.environ.get("ACCESS_PREFIX")
        self.storage_prefix = os.environ.get("STORAGE_PREFIX")

        self.job_max_duration = int(os.environ.get("JOB_MAX_DURATION") or 0) * 60

        self.idle_timeout = os.environ.get("IDLE_TIMEOUT")

        self.browser_image_template = os.environ.get("BROWSER_IMAGE_TEMPL")
        self.default_browser = os.environ.get("DEFAULT_BROWSER")
        self.driver_image = os.environ.get("DRIVER_IMAGE")

        self.job_prefix = "capture-"
        self.service_prefix = "service-"

        self.init_routes()

    def get_job_name(self, jobid):
        return self.job_prefix + jobid

    def get_service_name(self, jobid):
        return self.service_prefix + jobid

    def init_routes(self):
        # pylint: disable=unused-variable

        @self.app.get("/", response_class=HTMLResponse)
        async def read_item(request: Request):
            return self.templates.TemplateResponse("index.html", {"request": request})

        @self.app.post("/captures")
        async def start(capture: CaptureRequest):
            return await self.start_job(capture)

        @self.app.get("/captures")
        async def list_jobs(userid: str = ""):
            return await self.list_jobs(userid)

        @self.app.delete("/capture/{jobid}")
        async def delete_job(jobid: str, userid: str = ""):
            return await self.delete_job(jobid, userid)

        if self.use_vnc:

            @self.app.get("/attach/{jobid}", response_class=HTMLResponse)
            async def get_browser(jobid: str, request: Request):
                return self.render_browser(jobid, request)

            @self.app.get("/view/{browser}/{url:path}", response_class=HTMLResponse)
            async def load_browser(browser: str, url: str, request: Request):
                return await self.load_browser(browser, url, request)

            @self.app.post("/api/flock/start/{jobid}")
            async def flock_post(jobid: str):
                return await self.get_attach_data(jobid)

    async def start_job(self, capture: CaptureRequest):
        jobs = []

        print('EMBEDS', capture.embeds)

        for url in capture.urls:
            jobid = str(uuid.uuid4())

            filename = f"{ jobid }.wacz"
            storage_url = self.storage_prefix + filename

            try:
                download_filename = (
                    urllib.parse.urlsplit(url).netloc
                    + "-"
                    + str(datetime.datetime.utcnow())[:10]
                    + ".wacz"
                )
            except Exception as exc:
                print("Error Creating Download Filename", exc)
                download_filename = None

            access_url = await self.storage.get_presigned_url(
                storage_url, download_filename
            )

            jobs.append(
                self.init_browser_job(
                    browser=self.default_browser,
                    capture_url=url,
                    storage_url=storage_url,
                    access_url=access_url,
                    profile_url=self.profile_url,
                    userid=capture.userid,
                    driver_image=self.driver_image,
                    use_proxy=True,
                    job_max_duration=self.job_max_duration,
                    tag=capture.tag,
                    use_embeds=capture.embeds,
                )
            )

        job_ids = await asyncio.gather(*jobs)

        return {"urls": len(jobs), "jobids": job_ids}

    async def list_jobs(self, userid: str = ""):
        label_selector = []
        if userid:
            label_selector.append(f"userid={userid}")

        api_response = await self.k8s.list_jobs(label_selector=",".join(label_selector))

        jobs = []

        for job in api_response.items:
            data = job.metadata.labels
            data["captureUrl"] = job.metadata.annotations["captureUrl"]
            data["userTag"] = job.metadata.annotations["userTag"]
            data["startTime"] = job.status.start_time
            if job.metadata.annotations.get("useEmbeds") == "1":
                data["useEmbeds"] = True

            if job.status.completion_time:
                data["elapsedTime"] = job.status.completion_time
            else:
                data["elapsedTime"] = (
                    str(datetime.datetime.utcnow().isoformat())[:19] + "Z"
                )

            if job.status.active:
                data["status"] = "In progress"
            elif job.status.failed:
                data["status"] = "Failed"
            elif job.status.succeeded:
                data["status"] = "Complete"
                data["accessUrl"] = html.unescape(job.metadata.annotations["accessUrl"])
            else:
                data["status"] = "Unknown"

            jobs.append(data)

        return {"jobs": jobs}

    async def delete_job(self, jobid: str, userid: str = ""):
        api_response = await self.k8s.get_job(self.get_job_name(jobid))

        if userid and api_response.metadata.labels.get("userid") != userid:
            return {"deleted": False}

        if not api_response:
            return {"deleted": False}

        storage_url = api_response.metadata.annotations.get("storageUrl")
        if storage_url:
            await self.storage.delete_object(storage_url)

        api_response = await self.k8s.delete_job(self.get_job_name(jobid))

        api_response = await self.k8s.delete_service(self.get_service_name(jobid))

        return {"deleted": True}

    async def load_browser(self, browser: str, url: str, request: Request):
        if request.url.query:
            url += "?" + request.url.query

        jobid = await self.init_browser_job(
            browser=browser,
            capture_url=url,
            use_proxy=False,
            job_max_duration=self.job_max_duration,
            idle_timeout=self.idle_timeout,
        )

        return self.render_browser(jobid, request)

    async def init_browser_job(
        self,
        browser: str,
        capture_url: str,
        storage_url: str = "",
        access_url: str = "",
        start_url: str = "",
        profile_url: str = "",
        userid: str = "",
        driver_image: str = "",
        use_proxy: bool = False,
        job_max_duration: int = 0,
        idle_timeout: int = 0,
        tag: str = "",
        use_embeds: bool = False
    ):
        # pylint: disable=too-many-arguments,too-many-locals
        browser_image = self.browser_image_template.format(browser)

        if not start_url:
            start_url = capture_url if not driver_image else "about:blank"

        if not idle_timeout:
            idle_timeout = ""

        labels = {"userid": userid}

        annotations = {
            "userTag": tag,
            "captureUrl": capture_url,
            "storageUrl": storage_url,
            "accessUrl": access_url,
        }

        if use_embeds:
            annotations['useEmbeds'] = "1"

        jobid = str(uuid.uuid4())

        if self.use_vnc:
            annotations["vnc_pass"] = (str(uuid.uuid4()),)

        data = self.templates.env.get_template("browser-job.yaml").render(
            {
                "job_name": self.get_job_name(jobid),
                "jobid": jobid,
                "labels": labels,
                "annotations": annotations,
                "start_url": start_url,
                "capture_url": capture_url,
                "storage_url": storage_url,
                "profile_url": profile_url,
                "headless": self.headless,
                "vnc": self.use_vnc,
                "use_proxy": use_proxy,
                "browser_image": browser_image,
                "driver_image": driver_image,
                "job_max_duration": job_max_duration,
                "idle_timeout": idle_timeout,
                "use_embeds": use_embeds
            }
        )

        job = yaml.safe_load(data)

        await self.k8s.create_job(job)

        if self.use_vnc:
            data = self.templates.env.get_template("browser-service.yaml").render(
                {"service_name": self.get_service_name(jobid), "jobid": jobid}
            )

            service = yaml.safe_load(data)

            await self.k8s.create_service(service)

        return jobid

    async def get_attach_data(self, jobid):
        print("Getting job: " + self.get_job_name(jobid))
        api_response = await self.k8s.get_job(self.get_job_name(jobid))
        if not api_response:
            return {"not_found": True}

        name = self.get_service_name(jobid)
        password = api_response.metadata.annotations.get("vnc_pass")

        return {
            "containers": {
                "xserver": {
                    "ip": name,
                    "ports": {"cmd-port": 6082, "vnc-port": 6080},
                    "environ": {"VNC_PASS": password},
                }
            }
        }

    def render_browser(self, jobid, request):
        return self.templates.TemplateResponse(
            "browser.html",
            {
                "request": request,
                "jobid": jobid,
                "webrtc": False,
                "webrtc_video": False,
            },
        )


# ============================================================================
app = MainController().app
