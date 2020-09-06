import asyncio
import os
import datetime
from managers import K8SManager, StorageManager


# ============================================================================
async def delete_jobs(k8s, storage, cleanup_interval):
    api_response = await k8s.list_jobs()

    for job in api_response.items:
        if job.status.succeeded != 1:
            continue

        duration = datetime.datetime.utcnow() - job.status.start_time.replace(
            tzinfo=None
        )

        if duration < cleanup_interval:
            print("Keeping job {0}, not old enough".format(job.metadata.name))
            continue

        storage_url = job.metadata.annotations.get("storageUrl")
        if storage_url:
            try:
                print("Deleting archive file: " + storage_url)
                await storage.delete_object(storage_url)
                return True
            except Exception as exc:
                print(exc)
                return False

        print("Deleting job: " + job.metadata.name)

        await k8s.delete_job(job.metadata.name)

        await k8s.delete_service("service-" + job.metadata.name)


# ============================================================================
async def delete_pods(k8s, cleanup_interval):
    api_response = await k8s.list_pods(field_selector="status.phase=Succeeded")

    for pod in api_response.items:
        if (
            datetime.datetime.utcnow() - pod.status.start_time.replace(tzinfo=None)
        ) < cleanup_interval:
            print("Keeping pod {0}, not old enough".format(pod.metadata.name))
            continue

        await k8s.delete_pod(pod.metadata.name)


# ============================================================================
async def main():
    storage = StorageManager()
    k8s = K8SManager()

    cleanup_interval = datetime.timedelta(
        minutes=int(os.environ.get("JOB_CLEANUP_INTERVAL", 60))
    )

    print("Deleting jobs older than {0} minutes".format(cleanup_interval))

    await delete_jobs(k8s, storage, cleanup_interval)
    await delete_pods(k8s, cleanup_interval)
    print("Done!")


# ============================================================================
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()

#
