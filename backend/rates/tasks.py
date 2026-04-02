import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("rates")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_rates(self):
    """
    Scheduled task: re-runs the ingestion worker to pull latest rates.
    In production this would call a live scraper; here it logs a heartbeat.
    """
    logger.info(
        "Scheduled rate refresh started",
        extra={"task_id": self.request.id, "timestamp": timezone.now().isoformat()},
    )
    try:
        from django.core.management import call_command
        call_command("seed_data", "--skip-if-exists")
        logger.info("Scheduled rate refresh completed")
    except Exception as exc:
        logger.error("Scheduled rate refresh failed", extra={"error": str(exc)})
        raise self.retry(exc=exc)
