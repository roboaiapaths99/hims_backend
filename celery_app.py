from celery import Celery
from config import settings

celery_app = Celery(
    "hmis_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Make tasks run synchronously if test mode is enabled
    task_always_eager=False,
)

# Autodiscover from tasks.py
celery_app.autodiscover_tasks(["tasks"], force=True)
