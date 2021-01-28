from gevent.monkey import patch_all

patch_all()

import gevent
import sys

import requests
from urllib.parse import parse_qsl

from pywb.apps.frontendapp import FrontEndApp
from pywb.apps.cli import ReplayCli
from pywb.apps.wbrequestresponse import WbResponse
from warcio.timeutils import timestamp_now, timestamp_to_iso_date
from werkzeug.routing import Rule
import tempfile

import os
from wacz.main import main as wacz_main


def create_buff_func(params, name):
    return TempWriteBuffer(application, params.get("url", ""))


# ============================================================================
class CaptureApp(FrontEndApp):
    def __init__(self, *args, **kwargs):
        super(CaptureApp, self).__init__(*args, **kwargs)
        self.custom_record_path = (
            self.recorder_path + "&put_record={rec_type}&url={url}"
        )
        self.pending_count = 0
        self.pending_size = 0

    def init_recorder(self, *args, **kwargs):
        super(CaptureApp, self).init_recorder(*args, **kwargs)
        self.recorder.create_buff_func = create_buff_func

    def _init_routes(self):
        super(CaptureApp, self)._init_routes()
        self.url_map.add(
            Rule("/api/custom/<coll>", endpoint=self.put_custom_record, methods=["PUT"])
        )
        self.url_map.add(
            Rule("/api/pending", endpoint=self.get_pending, methods=["GET"])
        )
        self.url_map.add(
            Rule("/api/wacz/<coll>", endpoint=self.get_wacz, methods=["GET"])
        )
        self.url_map.add(Rule("/api/exit", endpoint=self.exit, methods=["GET"]))

    def get_pending(self, environ):
        return WbResponse.json_response(
            {"count": self.pending_count, "size": self.pending_size}
        )

    def exit(self, environ=None):
        import uwsgi
        import signal

        resp = WbResponse.json_response({})
        os.kill(uwsgi.masterpid(), signal.SIGTERM)
        return resp

    def get_wacz(self, environ, coll):
        # if self.pending_count != 0 or self.pending_size != 0:
        #    return WbResponse.json_response(
        #        {"error": "not_ready"}, status="404 Not Found"
        #    )

        params = dict(parse_qsl(environ.get("QUERY_STRING")))

        archive_dir = os.path.join("collections", coll, "archive")
        args = ['create', '-f']
        args += [
            os.path.join(archive_dir, name) for name in os.listdir(archive_dir)
        ]
        args.append("-o")
        args.append("/tmp/out/archive.wacz")

        url = params.get("url")
        if url:
            args.append("--url")
            args.append(url)

        try:
            wacz_main(args)
        except Exception as e:
            print(e)

        return WbResponse.json_response({"done": "/tmp/out/archive.wacz"})

    def put_custom_record(self, environ, coll):
        chunks = []
        while True:
            buff = environ["wsgi.input"].read()
            print("LEN", len(buff))
            if not buff:
                break

            chunks.append(buff)

        data = b"".join(chunks)

        params = dict(parse_qsl(environ.get("QUERY_STRING")))

        rec_type = "resource"

        headers = {"Content-Type": environ.get("CONTENT_TYPE", "text/plain")}

        target_uri = params.get("url")

        if not target_uri:
            return WbResponse.json_response({"error": "no url"})

        timestamp = params.get("timestamp")
        if timestamp:
            headers["WARC-Date"] = timestamp_to_iso_date(timestamp)

        put_url = self.custom_record_path.format(
            url=target_uri, coll=coll, rec_type=rec_type
        )
        res = requests.put(put_url, headers=headers, data=data)

        res = res.json()

        return WbResponse.json_response(res)


application = CaptureApp()


# ============================================================================
class TempWriteBuffer(tempfile.SpooledTemporaryFile):
    def __init__(self, app, url):
        super(TempWriteBuffer, self).__init__(max_size=512 * 1024)

        self.app = app
        self.app.pending_count += 1

        self.url = url

        print(
            "{1} {2} - Start Capture for {0}".format(
                self.url, self.app.pending_count, self.app.pending_size
            )
        )
        self._wsize = 0

    def write(self, buff):
        super(TempWriteBuffer, self).write(buff)
        length = len(buff)
        self._wsize += length

        self.app.pending_size += length

    def close(self):
        try:
            super(TempWriteBuffer, self).close()
        except:
            traceback.print_exc()

        self.app.pending_count -= 1
        print(
            "{1} {2} - End Capture for {0}".format(
                self.url, self.app.pending_count, self.app.pending_size
            )
        )
        self.app.pending_size -= self._wsize


# ============================================================================
# if __name__ == "__main__":
#    print('Starting pywb CaptureApp')
#    Cli().run()
