import os
import aiobotocore
import urllib.parse

from kubernetes_asyncio import client, config
from kubernetes_asyncio.utils.create_from_yaml import create_from_yaml_single_item
import os


# ============================================================================
if os.environ.get("BROWSER"):
    print("Cluster Init")
    config.load_incluster_config()
else:
    #loop = asyncio.get_event_loop()
    #loop.run_until_complete(main())
    config.load_kube_config()


# ============================================================================
class K8SManager:
    def __init__(self, namespace="browsers"):
        self.core_api = client.CoreV1Api()
        self.batch_api = client.BatchV1Api()
        self.namespace = namespace

    async def get_job(self, name):
        try:
            return await self.batch_api.read_namespaced_job(
                name=name, namespace=self.namespace
            )
        except Exception as e:
            print(e)
            return None

    async def create_job(self, job):
        api_response = await self.batch_api.create_namespaced_job(
            namespace=self.namespace, body=job
        )
        return api_response

    async def delete_job(self, name):
        api_response = await self.batch_api.delete_namespaced_job(
            name=name, namespace=self.namespace,
            propagation_policy="Foreground",
        )
        return api_response

    async def list_pods(self, field_selector=None):
        api_response = await self.core_api.list_namespaced_pod(
            namespace="browsers", field_selector=field_selector
        )
        return api_response

    async def delete_pod(self, name):
        await self.core_api.delete_namespaced_pod(pod.metadata.name, namespace="browsers")

    async def list_jobs(self, label_selector=None):
        api_response = await self.batch_api.list_namespaced_job(
            namespace=self.namespace
        )
        return api_response


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
