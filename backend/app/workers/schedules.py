"""Celery beat schedules."""

from __future__ import annotations

from celery.schedules import crontab

BEAT_SCHEDULE = {
    "revalidate-opportunities-hourly": {
        "task": "app.workers.tasks.revalidate_opportunities_task",
        "schedule": crontab(minute=15),
        "kwargs": {"limit": 200},
    },
    "scheduled-intelligence-digest": {
        "task": "app.workers.tasks.scheduled_digest_task",
        "schedule": crontab(hour=7, minute=0),
        "kwargs": {"since_hours": 24},
    },
}
