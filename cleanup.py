import asyncio
import os
import datetime
import aiobotocore
import urllib.parse
from k8smanager import K8SManager


# ============================================================================
class StorageManager:
    def __init__(self):
        self.session = aiobotocore.get_session()
        self.endpoint_url = os.environ.get("AWS_ENDPOINT", "")
        if not self.endpoint_url:
            self.endpoint_url = None

    async def delete_object(self, url):
        async with self.session.create_client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        ) as s3:
            parts = urllib.parse.urlsplit(url)
            resp = await s3.delete_object(Bucket=parts.netloc, Key=parts.path[1:])

    async def get_presigned_url(self, url, download_filename=None):
        async with self.session.create_client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        ) as s3:
            parts = urllib.parse.urlsplit(url)

            params = {"Bucket": parts.netloc, "Key": parts.path[1:]}

            if download_filename:
                params["ResponseContentDisposition"] = (
                    "attachment; filename=" + download_filename
                )

            return await s3.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=int(os.environ.get("JOB_CLEANUP_INTERVAL", 60)) * 60,
            )


# ============================================================================
async def main():
    minutes = os.environ.get("")

    storage = StorageManager()
    k8s = K8SManager()

    cleanup_interval = datetime.timedelta(
        minutes=int(os.environ.get("JOB_CLEANUP_INTERVAL", 60))
    )

    print("Deleting jobs older than {0} minutes".format(cleanup_interval))

    async def delete_obj(job):
        storageUrl = job.metadata.annotations.get("storageUrl")
        if storageUrl:
            try:
                print("Deleting archive file: " + storageUrl)
                await storage.delete_object(storageUrl)
                return True
            except Exception as e:
                print(e)
                return False

    await k8s.delete_jobs(cleanup_interval, delete_obj)
    await k8s.delete_pods(cleanup_interval)
    print("Done!")


# asyncio.run(main())
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()

#
