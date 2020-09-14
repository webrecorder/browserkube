import os
import uuid
import re
import yaml

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from managers import K8SManager, StorageManager


# ============================================================================
class BrowserKube:
    # pylint: disable=too-many-instance-attributes
    def __init__(self, allow_start_new=True):
        self.app = FastAPI()

        self.app.mount("/static", StaticFiles(directory="static"), name="static")

        self.templates = Jinja2Templates(directory="templates")

        self.storage = StorageManager()
        self.k8s = K8SManager()

        self.browser_image_template = os.environ.get("BROWSER_IMAGE_TEMPL")
        self.default_browser = os.environ.get("DEFAULT_BROWSER")

        with open(os.environ.get("JOB_ENV"), "rt") as config_fh:
            self.job_env = yaml.safe_load(config_fh.read()).get("config", {})

        self.browser_mode = self.job_env.get("mode")

        if not self.browser_mode:
            if self.job_env.get("enable_vnc"):
                self.browser_mode = "vnc"
            elif self.job_env.get("profile_url"):
                self.browser_mode = "xvfb"
            else:
                self.browser_mode = "headless"

        self.profile_urls = self.job_env.get("profile_urls") or {}
        for profile in self.profile_urls:
            profile["match"] = re.compile(profile["match"])

        self.job_prefix = "job-"
        self.service_prefix = "service-"

        self.allow_start_new = allow_start_new

        self.init_routes()

    def get_job_name(self, jobid):
        return self.job_prefix + jobid

    def get_service_name(self, jobid):
        return self.service_prefix + jobid

    def init_routes(self):
        # pylint: disable=unused-variable
        if self.allow_start_new:

            @self.app.post("/create/{browser}/{url:path}")
            async def create_browser_url(browser: str, url: str, request: Request):
                jobid = await self.create_browser(browser, url, request)
                return {"jobid": jobid}

            @self.app.delete("/browser/{jobid}")
            async def remove__browser(jobid: str, request: Request):
                return await self.remove_browser_job(jobid)

        if self.browser_mode == "vnc":

            @self.app.get("/attach/{jobid}", response_class=HTMLResponse)
            async def get_browser(jobid: str, request: Request):
                return self.render_browser(jobid, request)

            if self.allow_start_new:

                @self.app.get("/view/{browser}/{url:path}", response_class=HTMLResponse)
                async def load_browser(browser: str, url: str, request: Request):
                    jobid = await self.create_browser(browser, url, request)
                    return self.render_browser(jobid, request)

            @self.app.post("/api/flock/start/{jobid}")
            async def flock_post(jobid: str):
                return await self.get_attach_data(jobid)

    async def create_browser(self, browser: str, url: str, request: Request):
        if request.url.query:
            url += "?" + request.url.query

        jobid = await self.init_browser_job(
            browser=browser, start_url=url, use_proxy=False,
        )

        return jobid

    async def remove_browser_job(self, jobid):
        api_response = await self.k8s.delete_job(self.get_job_name(jobid))
        api_response = await self.k8s.delete_service(self.get_service_name(jobid))

        return {"deleted": True}

    async def init_browser_job(
        self,
        browser: str,
        labels: dict = None,
        annotations: dict = None,
        driver_env: dict = None,
        start_url: str = "",
        use_proxy: bool = False,
    ):
        # pylint: disable=too-many-arguments,too-many-locals
        browser_image = self.browser_image_template.format(browser)

        if not start_url:
            start_url = "about:blank"

        jobid = str(uuid.uuid4())

        annotations = annotations or {}
        labels = labels or {}
        driver_env = driver_env or {}

        # if has custom driver, set URL on image, set browser to blank
        if self.job_env.get("driver_image"):
            if "URL" not in driver_env and start_url:
                driver_env["URL"] = start_url
                url = start_url
            start_url = "about:blank"
        else:
            url = start_url

        if self.browser_mode == "vnc":
            annotations["vnc_pass"] = str(uuid.uuid4())

        config = {
            "job_name": self.get_job_name(jobid),
            "jobid": jobid,
            "browser_image": browser_image,
            "labels": labels,
            "annotations": annotations,
            "driver_env": driver_env,
            "start_url": start_url,
            "use_proxy": use_proxy,
        }

        config.update(self.job_env)

        # determine if a profile should be used for this url
        if self.profile_urls:
            for profile in self.profile_urls:
                if profile["match"].match(url):
                    config["profile_url"] = profile["url"]
                    if config["mode"] == "headless":
                        config["mode"] = "xvfb"

        print(config)

        data = self.templates.env.get_template("browser-job.yaml").render(config)

        job = yaml.safe_load(data)

        await self.k8s.create_job(job)

        if self.browser_mode == "vnc" or self.job_env.get("remote_cdp"):
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
app = BrowserKube().app
