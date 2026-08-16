"""Heuristic tool-selection benchmark for Phase 5 exit criteria."""

from __future__ import annotations

from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolArgumentCase, ToolSelectionCase

_SELECTION_CASES: tuple[ToolSelectionCase, ...] = (
    ToolSelectionCase(
        prompt="Find grants matching my profile",
        expected_tool="search_opportunities",
    ),
    ToolSelectionCase(
        prompt="Search my uploaded CV for leadership experience",
        expected_tool="search_user_documents",
    ),
    ToolSelectionCase(
        prompt="What does my profile say about remote work?",
        expected_tool="search_user_profile",
    ),
    ToolSelectionCase(
        prompt="Score this opportunity against my goal",
        expected_tool="calculate_opportunity_score",
    ),
    ToolSelectionCase(
        prompt="Check if I am eligible for this grant",
        expected_tool="check_eligibility",
    ),
    ToolSelectionCase(
        prompt="Fetch the public posting from this URL",
        expected_tool="search_web",
    ),
    ToolSelectionCase(
        prompt="Research Acme Corp before applying",
        expected_tool="research_company",
    ),
    ToolSelectionCase(
        prompt="When is the application deadline?",
        expected_tool="extract_deadline",
    ),
    ToolSelectionCase(
        prompt="Show opportunities I investigated last week",
        expected_tool="get_previous_opportunities",
    ),
    ToolSelectionCase(
        prompt="Save this new fellowship to the database",
        expected_tool="save_opportunity",
    ),
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "search_opportunities": ("find", "search", "matching", "grants", "jobs", "list"),
    "search_user_documents": ("uploaded", "cv", "resume", "document"),
    "search_user_profile": ("profile", "my background", "about me"),
    "calculate_opportunity_score": ("score", "rank", "evaluate numerically"),
    "check_eligibility": ("eligible", "eligibility", "qualify"),
    "search_web": ("fetch", "url", "website", "public posting"),
    "research_company": ("research", "company", "organisation", "organization"),
    "extract_deadline": ("deadline", "due date", "closing date"),
    "get_previous_opportunities": ("previous", "investigated", "last week", "history"),
    "save_opportunity": ("save", "store", "ingest", "new fellowship"),
    "get_company_information": ("company information", "organisation details"),
    "create_follow_up": ("follow up", "follow-up", "reminder"),
    "prepare_application": ("prepare application", "checklist", "application draft"),
    "generate_outreach": ("outreach", "email draft", "cover letter"),
    "update_opportunity_status": ("update status", "archive", "mark as"),
}


def suggest_tool(prompt: str, registry: ToolRegistry) -> str:
    """Keyword router used by the benchmark — not an LLM."""
    lowered = prompt.casefold()
    best_name = registry.names()[0]
    best_score = -1
    for name, keywords in _KEYWORDS.items():
        if name not in registry.names():
            continue
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name


def selection_accuracy(registry: ToolRegistry) -> float:
    hits = 0
    for case in _SELECTION_CASES:
        if suggest_tool(case.prompt, registry) == case.expected_tool:
            hits += 1
    return hits / len(_SELECTION_CASES)


def selection_cases() -> tuple[ToolSelectionCase, ...]:
    return _SELECTION_CASES


def argument_cases() -> tuple[ToolArgumentCase, ...]:
    import uuid

    goal_id = uuid.uuid4()
    opp_id = uuid.uuid4()
    return (
        ToolArgumentCase(
            tool_name="search_opportunities",
            arguments={"query": "climate grant"},
            valid=True,
        ),
        ToolArgumentCase(
            tool_name="search_opportunities",
            arguments={"query": ""},
            valid=False,
        ),
        ToolArgumentCase(
            tool_name="calculate_opportunity_score",
            arguments={"opportunity_id": str(opp_id), "goal_id": str(goal_id)},
            valid=True,
        ),
        ToolArgumentCase(
            tool_name="calculate_opportunity_score",
            arguments={"opportunity_id": "not-a-uuid", "goal_id": str(goal_id)},
            valid=False,
        ),
        ToolArgumentCase(
            tool_name="search_user_profile",
            arguments={"query": "skills", "top_k": 5},
            valid=True,
        ),
        ToolArgumentCase(
            tool_name="generate_outreach",
            arguments={"opportunity_id": str(opp_id), "channel": "email"},
            valid=True,
        ),
    )


def argument_validity(registry: ToolRegistry) -> float:
    cases = argument_cases()
    hits = 0
    for case in cases:
        tool = registry.get(case.tool_name)
        try:
            tool.parse_args(case.arguments)
            ok = True
        except Exception:
            ok = False
        if ok == case.valid:
            hits += 1
    return hits / len(cases)
