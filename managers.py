import os
import urllib.parse

import aiobotocore
from kubernetes_asyncio import client, config


# ============================================================================
if os.environ.get("IN_CLUSTER"):
    print("Cluster Init")
    config.load_incluster_config()
else:
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(main())
    config.load_kube_config()


DEFAULT_NAMESPACE = os.environ.get("BROWSER_NAMESPACE") or "browsers"


# ============================================================================
class K8SManager:
    def __init__(self, namespace=DEFAULT_NAMESPACE):
        self.core_api = client.CoreV1Api()
        self.batch_api = client.BatchV1Api()
        self.namespace = namespace

    async def get_job(self, name):
        try:
            return await self.batch_api.read_namespaced_job(
                name=name, namespace=self.namespace
            )
        except Exception as exc:
            print(exc)
            return None

    async def create_job(self, job):
        api_response = await self.batch_api.create_namespaced_job(
            namespace=self.namespace, body=job
        )
        return api_response

    async def delete_job(self, name):
        api_response = await self.batch_api.delete_namespaced_job(
            name=name, namespace=self.namespace, propagation_policy="Foreground",
        )
        return api_response

    async def list_pods(self, field_selector=None):
        api_response = await self.core_api.list_namespaced_pod(
            namespace="browsers", field_selector=field_selector
        )
        return api_response

    async def delete_pod(self, name):
        await self.core_api.delete_namespaced_pod(name, namespace=self.namespace)

    async def list_jobs(self, label_selector=None):
        api_response = await self.batch_api.list_namespaced_job(
            namespace=self.namespace, label_selector=label_selector
        )
        return api_response

    async def create_service(self, service):
        api_response = await self.core_api.create_namespaced_service(
            body=service, namespace=self.namespace
        )
        return api_response

    async def delete_service(self, name):
        try:
            api_response = await self.core_api.delete_namespaced_service(
                name, namespace=self.namespace
            )
            return api_response
        except client.exceptions.ApiException as exc:
            if exc.status != 404:
                raise


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
        ) as s3_client:
            parts = urllib.parse.urlsplit(url)
            resp = await s3_client.delete_object(
                Bucket=parts.netloc, Key=parts.path[1:]
            )

            return resp

    async def get_presigned_url(self, url, download_filename=None):
        async with self.session.create_client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        ) as s3_client:
            parts = urllib.parse.urlsplit(url)

            params = {"Bucket": parts.netloc, "Key": parts.path[1:]}

            if download_filename:
                params["ResponseContentDisposition"] = (
                    "attachment; filename=" + download_filename
                )

            return await s3_client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=int(os.environ.get("JOB_CLEANUP_INTERVAL", 60)) * 60,
            )
