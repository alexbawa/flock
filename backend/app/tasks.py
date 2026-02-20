from celery import shared_task


@shared_task
def run_job(job_id: str) -> None:
    # TODO: implement flight search fan-out
    pass
