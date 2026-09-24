import json
from datetime import datetime
from zoneinfo import ZoneInfo

from weather_checker import healthcheck
from weather_checker.scheduler import build_scheduler

BERLIN = ZoneInfo("Europe/Berlin")


def _next_run(job_id: str, after: datetime) -> datetime:
    scheduler = build_scheduler("Europe/Berlin")
    trigger = scheduler.get_job(job_id).trigger
    return trigger.get_next_fire_time(None, after)


def test_morning_job_stays_at_seven_after_spring_dst_change():
    next_run = _next_run(
        "morning_forecast",
        datetime(2026, 3, 28, 8, 0, tzinfo=BERLIN),
    )

    assert next_run == datetime(2026, 3, 29, 7, 0, tzinfo=BERLIN)
    assert next_run.utcoffset().total_seconds() == 2 * 60 * 60


def test_night_job_stays_at_twenty_after_autumn_dst_change():
    next_run = _next_run(
        "night_forecast",
        datetime(2026, 10, 24, 21, 0, tzinfo=BERLIN),
    )

    assert next_run == datetime(2026, 10, 25, 20, 0, tzinfo=BERLIN)
    assert next_run.utcoffset().total_seconds() == 60 * 60


def test_scheduler_has_exactly_the_two_expected_wall_clock_jobs():
    scheduler = build_scheduler("Europe/Berlin")

    jobs = {job.id: str(job.trigger) for job in scheduler.get_jobs()}
    assert set(jobs) == {"morning_forecast", "night_forecast"}
    assert "hour='7'" in jobs["morning_forecast"]
    assert "hour='20'" in jobs["night_forecast"]


def test_healthcheck_fails_after_a_failed_delivery(tmp_path, monkeypatch):
    state_file = tmp_path / "health.json"
    monkeypatch.setattr(healthcheck, "HEALTH_FILE", state_file)
    healthcheck.record_run(
        "morning",
        success=False,
        started_at=datetime(2026, 9, 24, 7, 0, tzinfo=BERLIN),
        error="recipient 3 failed",
    )

    assert healthcheck.main() == 1
    assert json.loads(state_file.read_text())["error"] == "recipient 3 failed"


def test_healthcheck_passes_after_all_recipients_receive(tmp_path, monkeypatch):
    state_file = tmp_path / "health.json"
    monkeypatch.setattr(healthcheck, "HEALTH_FILE", state_file)
    healthcheck.record_run(
        "night",
        success=True,
        started_at=datetime(2026, 9, 24, 20, 0, tzinfo=BERLIN),
        recipient_count=3,
    )

    assert healthcheck.main() == 0
    assert json.loads(state_file.read_text())["recipient_count"] == 3
