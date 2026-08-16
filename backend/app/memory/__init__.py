"""Memory subsystem (Phase 6).

Four kinds, three of them persistent:

* short-term  — the LangGraph checkpointed state of the current run
* episodic    — previous investigations and their conclusions
* semantic    — durable facts about the user's profile and preferences
* outcome     — what actually happened, used to recalibrate scoring

Writes are append-only with provenance: a contradicted record is closed with
``valid_to`` and linked through ``superseded_by_id``. Memory must never mutate
an existing fact in place.
"""
