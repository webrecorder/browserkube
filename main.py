from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, FileResponse

from pydantic import BaseModel

import os
import base64
import yaml
import html

import urllib.parse
import datetime

import aiohttp

from managers import K8SManager, StorageManager


class CaptureRequest(BaseModel):
    urls: List[str]
    userid: str = "user"
    tag: str = ""


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/replay", StaticFiles(directory="replay"), name="replay")

templates = Jinja2Templates(directory="templates")

profile_url = os.environ.get("PROFILE_URL", "")
headless = not profile_url

use_vnc = os.environ.get("VNC") and not headless

access_prefix = os.environ.get("ACCESS_PREFIX")
storage_prefix = os.environ.get("STORAGE_PREFIX")

job_max_duration = int(os.environ.get("JOB_MAX_DURATION") or 0) * 60

storage = StorageManager()
k8s = K8SManager()


def make_jobid():
    return base64.b32encode(os.urandom(15)).decode("utf-8").lower()


def get_job_name(jobid, index):
    return f"capture-{jobid}-{index}"


@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/browser/{jobname}", response_class=HTMLResponse)
async def get_browser(jobname: str, request: Request):
    return templates.TemplateResponse(
        "browser.html",
        {
            "request": request,
            "jobname": jobname,
            "webrtc": False,
            "webrtc_video": False,
        },
    )


@app.post("/api/flock/start/{jobname}")
async def flock_post(jobname: str, request: Request):
    api_response = await k8s.get_job(jobname)
    if not api_response:
        return {"not_found": True}

    return {
        "containers": {
            "xserver": {
                "ip": "service-" + jobname,
                "ports": {"cmd-port": 6082, "vnc-port": 6080},
                "environ": {"VNC_PASS": api_response.metadata.annotations.get("vnc_pass")},
            }
        }
    }


@app.post("/captures")
async def start(capture: CaptureRequest):
    return await start_job(capture)


@app.delete("/capture/{jobid}/{index}")
async def delete_job(jobid: str, index: str):
    name = get_job_name(jobid, index)

    api_response = await k8s.get_job(name)
    if not api_response:
        return {"deleted": False}

    storage_url = api_response.metadata.annotations.get("storageUrl")
    if storage_url:
        await storage.delete_object(storage_url)

    api_response = await k8s.delete_job(name)

    api_response = await k8s.delete_service("service-" + name)

    return {"deleted": True}


@app.get("/captures")
async def list_jobs(jobid: str = "", userid: str = "", index: int = -1):
    label_selector = []
    if jobid:
        label_selector.append(f"jobid={jobid}")

    if userid:
        label_selector.append(f"userid={userid}")

    if index >= 0:
        label_selector.append(f"index={index}")

    api_response = await k8s.list_jobs(label_selector == ",".join(label_selector))

    jobs = []

    for job in api_response.items:
        data = job.metadata.labels
        data["captureUrl"] = job.metadata.annotations["captureUrl"]
        data["userTag"] = job.metadata.annotations["userTag"]
        data["startTime"] = job.status.start_time

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


async def start_job(capture: CaptureRequest):
    jobid = make_jobid()

    index = 0
    for url in capture.urls:
        job_name = get_job_name(jobid, index)

        filename = f"{ jobid }/{ index }.wacz"
        storage_url = storage_prefix + filename

        try:
            download_filename = (
                urllib.parse.urlsplit(url).netloc
                + "-"
                + str(datetime.datetime.utcnow())[:10]
                + ".wacz"
            )
        except:
            download_filename = None

        access_url = await storage.get_presigned_url(storage_url, download_filename)

        labels = {"userid": capture.userid, "jobid": jobid, "index": index}

        annotations = {
            "userTag": capture.tag,
            "accessUrl": access_url,
            "captureUrl": url,
            "storageUrl": storage_url,
            "vnc_pass": make_jobid()
        }

        data = templates.env.get_template("browser-job.yaml").render(
            {
                "job_name": job_name,
                "labels": labels,
                "annotations": annotations,
                "capture_url": url,
                "storage_url": storage_url,
                "profile_url": profile_url,
                "headless": headless,
                "vnc": use_vnc,
                "job_max_duration": job_max_duration,
            }
        )

        job = yaml.safe_load(data)

        res = await k8s.create_job(job)

        if use_vnc:
            data = templates.env.get_template("browser-service.yaml").render(
                {"job_name": job_name}
            )

            service = yaml.safe_load(data)

            res = await k8s.create_service(service)

        index += 1

    return {"jobid": jobid, "urls": index}
