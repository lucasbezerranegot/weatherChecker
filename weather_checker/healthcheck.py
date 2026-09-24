"""Small persistent health signal for the scheduler container."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

HEALTH_FILE = Path(os.environ.get("HEALTH_FILE", "/tmp/weather-checker-health.json"))


def record_run(
    mode: str,
    success: bool,
    started_at: datetime,
    recipient_count: int | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "mode": mode,
        "success": success,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(started_at.tzinfo).isoformat(),
    }
    if recipient_count is not None:
        payload["recipient_count"] = recipient_count
    if error:
        payload["error"] = error
    temporary = HEALTH_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(HEALTH_FILE)


def main() -> int:
    # Before the first scheduled execution, the running scheduler is healthy.
    if not HEALTH_FILE.exists():
        return 0
    try:
        state = json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 1
    return 0 if state.get("success") is True else 1


if __name__ == "__main__":
    sys.exit(main())
