"""Specialised agents and LangGraph orchestration (Phase 4-6).

Contract fixed in docs/AGENT_DESIGN.md. Every agent will be a class exposing::

    card: AgentCard                       # identity, capabilities, schemas
    async def run(self, payload: InputModel, ctx: RunContext) -> OutputModel

with providers injected, so each agent is unit-testable against a fake LLM and
can later be promoted to a remote A2A agent without touching its call sites.
This package must never import ``app.api``.
"""
