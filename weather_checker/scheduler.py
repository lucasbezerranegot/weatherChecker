"""Long-running scheduler for local Docker deployments."""

import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .healthcheck import record_run
from .service import run_forecast

LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "Europe/Berlin"


def build_scheduler(timezone_name: str | None = None) -> BlockingScheduler:
    """Create the two daily wall-clock jobs in the configured timezone."""
    timezone = ZoneInfo(
        timezone_name or os.environ.get("SCHEDULER_TIMEZONE", DEFAULT_TIMEZONE)
    )
    scheduler = BlockingScheduler(
        timezone=timezone,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 30 * 60,
        },
    )
    scheduler.add_job(
        scheduled_forecast,
        CronTrigger(hour=7, minute=0, timezone=timezone),
        args=["morning"],
        id="morning_forecast",
        name="Previsão da manhã",
    )
    scheduler.add_job(
        scheduled_forecast,
        CronTrigger(hour=20, minute=0, timezone=timezone),
        args=["night"],
        id="night_forecast",
        name="Previsão da noite",
    )
    return scheduler


def scheduled_forecast(mode: str) -> None:
    """Run one forecast and expose the outcome to Docker's health check."""
    started_at = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    try:
        messages = run_forecast(mode)
    except Exception as exc:
        record_run(mode, success=False, started_at=started_at, error=str(exc))
        LOGGER.exception("Falha no relatório %s", mode)
        raise
    record_run(mode, success=True, started_at=started_at, recipient_count=len(messages))
    LOGGER.info("Relatório %s enviado para %d destinatário(s)", mode, len(messages))


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    scheduler = build_scheduler()
    LOGGER.info("Scheduler iniciado; próximos envios às 07:00 e 20:00 (%s)", scheduler.timezone)
    scheduler.start()


if __name__ == "__main__":
    main()
