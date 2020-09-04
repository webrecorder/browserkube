from kubernetes_asyncio import client, config
from kubernetes_asyncio.utils.create_from_yaml import create_from_yaml_single_item
import os

if os.environ.get("BROWSER"):
    print("Cluster Init")
    config.load_incluster_config()
else:
    #loop = asyncio.get_event_loop()
    #loop.run_until_complete(main())
    config.load_kube_config()


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

    async def list_pod(self, name, field_selector=None):
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

    async def delete_jobs(self, cleanup_interval, callback=None):
        api_response = await self.list_jobs()

        for job in api_response.items:
            if job.status.succeeded != 1:
                continue

            duration = datetime.datetime.utcnow() - job.status.start_time.replace(
                tzinfo=None
            )

            if duration < cleanup_interval:
                print("Keeping job {0}, not old enough".format(job.metadata.name))
                continue

            if callback:
                if not await callback(job.metadata):
                    return False

            print("Deleting job: " + job.metadata.name)

            await self.delete_job(job.metadata.name)

    async def delete_pods(cleanup_interval):
        api_response = await self.list_pods(field_selector="status.phase=Succeeded")

        for pod in api_response.items:
            if (
                datetime.datetime.utcnow() - pod.status.start_time.replace(tzinfo=None)
            ) < cleanup_interval:
                print("Keeping pod {0}, not old enough".format(pod.metadata.name))
                continue

            await self.delete_pod(self.metadata.name)

