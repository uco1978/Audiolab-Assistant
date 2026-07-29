import asyncio
import json
import logging

from app.config import get_settings
from app.db import claim_next_queue_job, complete_queue_job, fail_queue_job, get_job, init_db, update_job
from app.jobs.runner import run_job
from app.models import JobStatus
from app.secrets_store import apply_provider_secrets_to_runtime

log = logging.getLogger("ppc.worker")


async def worker_loop() -> None:
    await init_db()
    await apply_provider_secrets_to_runtime()
    settings = get_settings()
    log.info("Worker started (poll=%ss)", settings.worker_poll_seconds)
    while True:
        # Pick up keys saved via Settings without requiring a worker redeploy.
        await apply_provider_secrets_to_runtime()
        queue_item = await claim_next_queue_job()
        if not queue_item:
            await asyncio.sleep(settings.worker_poll_seconds)
            continue

        queue_id = queue_item["id"]
        job_id = queue_item["job_id"]
        payload = json.loads(queue_item.get("payload") or "{}")
        url = payload.get("url")
        config = payload.get("config", {})
        attempts = int(queue_item.get("attempts", 1))
        max_attempts = int(queue_item.get("max_attempts", settings.worker_max_retries))

        try:
            if not url:
                raise RuntimeError("Queue payload missing URL")
            log.info("Processing job=%s queue=%s attempt=%s", job_id, queue_id, attempts)
            await run_job(job_id, url, config)
            job = await get_job(job_id)
            if job and job.status == JobStatus.CANCELLED:
                await fail_queue_job(queue_id, attempts=max_attempts, max_attempts=max_attempts)
                log.info("Cancelled job=%s queue=%s", job_id, queue_id)
            else:
                await complete_queue_job(queue_id)
                log.info("Completed job=%s queue=%s", job_id, queue_id)
        except Exception as exc:
            job = await get_job(job_id)
            if job and job.status == JobStatus.CANCELLED:
                await fail_queue_job(queue_id, attempts=max_attempts, max_attempts=max_attempts)
                log.info("Cancelled job=%s queue=%s (during error)", job_id, queue_id)
            else:
                await update_job(job_id, status=JobStatus.FAILED.value, error=str(exc))
                await fail_queue_job(queue_id, attempts=attempts, max_attempts=max_attempts)
                log.exception("Failed job=%s queue=%s attempt=%s", job_id, queue_id, attempts)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    )
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
