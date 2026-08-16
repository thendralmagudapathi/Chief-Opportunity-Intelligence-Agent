"""Background processing (Phase 10).

Celery application, task definitions and beat schedules for discovery,
revalidation, embedding generation, evaluation and the scheduled-intelligence
digest. API requests never block on agent work: an investigation is enqueued and
observed over SSE.
"""
