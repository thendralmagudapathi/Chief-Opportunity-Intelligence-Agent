"""Native tool implementations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import ValidationError
from app.models.agent_run import AgentRun
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.goal import Goal
from app.models.opportunity import Opportunity
from app.models.user import UserProfile
from app.schemas.opportunity import OpportunityFilters
from app.services import factors
from app.services.ingestion import IngestionService, RawOpportunity
from app.services.normalization import DateOutcome, parse_deadline
from app.services.opportunity_service import OpportunityService
from app.services.retrieval_service import build_retrieval_service
from app.services.scoring_service import ScoringService
from app.tools.base import BaseTool
from app.tools.context import ToolContext
from app.tools.errors import ToolNotFoundError
from app.tools.permissions import (
    SCOPE_APPLICATION_WRITE,
    SCOPE_DOCUMENT_READ,
    SCOPE_EXTERNAL_COMMUNICATE,
    SCOPE_OPPORTUNITY_READ,
    SCOPE_OPPORTUNITY_WRITE,
    SCOPE_PROFILE_READ,
    SCOPE_WEB_FETCH,
)
from app.tools.schemas import (
    CalculateOpportunityScoreArgs,
    CheckEligibilityArgs,
    CreateFollowUpArgs,
    ExtractDeadlineArgs,
    GenerateOutreachArgs,
    GetCompanyInformationArgs,
    GetPreviousOpportunitiesArgs,
    PrepareApplicationArgs,
    ResearchCompanyArgs,
    SaveOpportunityArgs,
    SearchOpportunitiesArgs,
    SearchUserDocumentsArgs,
    SearchUserProfileArgs,
    SearchWebArgs,
    UpdateOpportunityStatusArgs,
)
from app.tools.types import SideEffect


async def _profile_for(ctx: ToolContext) -> UserProfile | None:
    result = await ctx.session.execute(
        select(UserProfile).where(UserProfile.user_id == ctx.user_id)
    )
    return result.scalar_one_or_none()


class SearchOpportunitiesTool(BaseTool):
    name = "search_opportunities"
    description = "Search indexed opportunities with optional filters."
    args_model = SearchOpportunitiesArgs
    permission_scope = SCOPE_OPPORTUNITY_READ
    max_calls_per_run = 20

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = SearchOpportunitiesArgs.model_validate(args)
        service = OpportunityService(ctx.session)
        page = await service.list_opportunities(
            OpportunityFilters(
                q=payload.query,
                goal_id=payload.goal_id or ctx.goal_id,
                category=payload.category,
            ),
            limit=payload.limit,
        )
        return {
            "items": [
                {
                    "id": str(row.opportunity.id),
                    "title": row.opportunity.title,
                    "organization_name": row.opportunity.organization_name,
                    "status": row.opportunity.status.value,
                    "overall_score": float(row.score.overall_score) if row.score else None,
                }
                for row in page.rows
            ],
            "has_more": page.has_more,
        }


class SearchWebTool(BaseTool):
    name = "search_web"
    description = "Fetch a public web page or return a stubbed search summary."
    args_model = SearchWebArgs
    permission_scope = SCOPE_WEB_FETCH
    timeout_s = 45.0
    max_calls_per_run = 8

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = SearchWebArgs.model_validate(args)
        if payload.url is not None:
            if ctx.http is None:
                raise ValidationError("HTTP client unavailable")
            result = await ctx.http.fetch(str(payload.url))
            external = ctx.http.as_external(result)
            return {
                "url": result.url,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "retrieved_at": result.retrieved_at.isoformat(),
                "excerpt": external.text[:2000],
                "trust": external.trust.name,
            }
        return {
            "query": payload.query,
            "results": [],
            "note": "Direct URL fetch is required; generic web search is not configured.",
        }


class ResearchCompanyTool(BaseTool):
    name = "research_company"
    description = "Summarise a company from stored opportunities and optional web fetch."
    args_model = ResearchCompanyArgs
    permission_scope = SCOPE_WEB_FETCH
    max_calls_per_run = 8

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = ResearchCompanyArgs.model_validate(args)
        stmt = (
            select(Opportunity)
            .where(Opportunity.organization_name.ilike(f"%{payload.company_name}%"))
            .order_by(Opportunity.created_at.desc())
            .limit(5)
        )
        rows = list((await ctx.session.execute(stmt)).scalars())
        web_excerpt: str | None = None
        if payload.domain and ctx.http is not None:
            try:
                fetched = await ctx.http.fetch(f"https://{payload.domain}")
                web_excerpt = fetched.body[:1500]
            except ValidationError:
                web_excerpt = None
        return {
            "company_name": payload.company_name,
            "domain": payload.domain,
            "known_opportunities": [
                {
                    "id": str(row.id),
                    "title": row.title,
                    "source_url": row.source_url,
                }
                for row in rows
            ],
            "web_excerpt": web_excerpt,
        }


class GetCompanyInformationTool(BaseTool):
    name = "get_company_information"
    description = "Return organisation fields for a stored opportunity."
    args_model = GetCompanyInformationArgs
    permission_scope = SCOPE_OPPORTUNITY_READ

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = GetCompanyInformationArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        return {
            "opportunity_id": str(opportunity.id),
            "organization_name": opportunity.organization_name,
            "organization_domain": opportunity.organization_domain,
            "location_country": opportunity.location_country,
            "location_city": opportunity.location_city,
            "source_url": opportunity.source_url,
        }


class ExtractDeadlineTool(BaseTool):
    name = "extract_deadline"
    description = "Parse a deadline from opportunity data or free text."
    args_model = ExtractDeadlineArgs
    permission_scope = SCOPE_OPPORTUNITY_READ

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = ExtractDeadlineArgs.model_validate(args)
        text = payload.text
        if payload.opportunity_id is not None:
            opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
            if opportunity is None:
                raise ToolNotFoundError("Opportunity not found")
            if opportunity.deadline is not None:
                return {
                    "deadline": opportunity.deadline.isoformat(),
                    "source": "stored",
                    "ambiguous": False,
                }
            text = " ".join(filter(None, [opportunity.summary, opportunity.description]))
        if not text:
            raise ValidationError("Provide opportunity_id or text")
        parsed = parse_deadline(text)
        return {
            "deadline": parsed.value.isoformat() if parsed.value else None,
            "source": "parsed",
            "ambiguous": parsed.outcome == DateOutcome.AMBIGUOUS,
            "outcome": parsed.outcome.value,
        }


class CheckEligibilityTool(BaseTool):
    name = "check_eligibility"
    description = "Evaluate deterministic eligibility signals for an opportunity."
    args_model = CheckEligibilityArgs
    permission_scope = SCOPE_PROFILE_READ

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = CheckEligibilityArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        goal_id = payload.goal_id or ctx.goal_id
        goal = await ctx.session.get(Goal, goal_id) if goal_id else None
        profile = await _profile_for(ctx)
        derived = factors.derive(opportunity, profile=profile, goal=goal)
        verdict = "eligible"
        if derived.eligible is False:
            verdict = "ineligible"
        elif derived.eligible is None:
            verdict = "unknown"
        return {
            "opportunity_id": str(opportunity.id),
            "verdict": verdict,
            "eligible": derived.eligible,
            "days_to_deadline": derived.days_to_deadline,
            "rationale": derived.rationale,
        }


class SearchUserProfileTool(BaseTool):
    name = "search_user_profile"
    description = "Hybrid retrieval over the user's profile knowledge index."
    args_model = SearchUserProfileArgs
    permission_scope = SCOPE_PROFILE_READ
    max_calls_per_run = 15

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = SearchUserProfileArgs.model_validate(args)
        retrieval = build_retrieval_service(ctx.session, ctx.settings)
        result = await retrieval.search_profile(
            user_id=ctx.user_id,
            query=payload.query,
            top_k=payload.top_k,
            rerank=True,
        )
        return {
            "query": result.query,
            "passages": [
                {
                    "content": passage.content,
                    "score": passage.score,
                    "channel": passage.channel,
                    "document_id": str(passage.document_id) if passage.document_id else None,
                }
                for passage in result.passages
            ],
            "degraded": result.degraded,
        }


class SearchUserDocumentsTool(BaseTool):
    name = "search_user_documents"
    description = "Retrieve passages from uploaded documents for the current user."
    args_model = SearchUserDocumentsArgs
    permission_scope = SCOPE_DOCUMENT_READ
    max_calls_per_run = 15

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = SearchUserDocumentsArgs.model_validate(args)
        retrieval = build_retrieval_service(ctx.session, ctx.settings)
        result = await retrieval.search_profile(
            user_id=ctx.user_id,
            query=payload.query,
            top_k=payload.top_k,
            rerank=True,
        )
        document_passages = [passage for passage in result.passages if passage.document_id is not None]
        return {
            "query": result.query,
            "passages": [
                {
                    "content": passage.content,
                    "score": passage.score,
                    "document_id": str(passage.document_id) if passage.document_id else None,
                }
                for passage in document_passages[: payload.top_k]
            ],
            "degraded": result.degraded,
        }


class CalculateOpportunityScoreTool(BaseTool):
    name = "calculate_opportunity_score"
    description = "Score an opportunity against a goal and persist the result."
    args_model = CalculateOpportunityScoreArgs
    permission_scope = SCOPE_OPPORTUNITY_WRITE
    side_effects = SideEffect.INTERNAL_WRITE
    max_calls_per_run = 20

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = CalculateOpportunityScoreArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        goal = await ctx.session.get(Goal, payload.goal_id)
        if opportunity is None or goal is None:
            raise ToolNotFoundError("Opportunity or goal not found")
        if goal.user_id != ctx.user_id:
            raise ToolNotFoundError("Goal not found")
        profile = await _profile_for(ctx)
        row = await ScoringService(ctx.session).score_opportunity(
            opportunity, goal, profile=profile
        )
        return {
            "opportunity_id": str(opportunity.id),
            "goal_id": str(goal.id),
            "overall_score": float(row.overall_score),
            "confidence": float(row.confidence or 0),
            "recommendation": row.recommendation.value if row.recommendation else None,
        }


class GetPreviousOpportunitiesTool(BaseTool):
    name = "get_previous_opportunities"
    description = "List opportunities the user has previously investigated."
    args_model = GetPreviousOpportunitiesArgs
    permission_scope = SCOPE_OPPORTUNITY_READ

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = GetPreviousOpportunitiesArgs.model_validate(args)
        stmt = (
            select(AgentRun)
            .where(AgentRun.user_id == ctx.user_id)
            .order_by(AgentRun.created_at.desc())
            .limit(payload.limit)
        )
        runs = list((await ctx.session.execute(stmt)).scalars())
        seen: set[uuid.UUID] = set()
        items: list[dict[str, Any]] = []
        for run in runs:
            focus_ids = run.budget.get("opportunity_ids") if run.budget else None
            if not focus_ids:
                continue
            for raw_id in focus_ids:
                opp_id = uuid.UUID(str(raw_id))
                if opp_id in seen:
                    continue
                opportunity = await ctx.session.get(Opportunity, opp_id)
                if opportunity is None:
                    continue
                seen.add(opp_id)
                items.append(
                    {
                        "id": str(opportunity.id),
                        "title": opportunity.title,
                        "status": opportunity.status.value,
                        "last_run_id": str(run.id),
                    }
                )
        return {"items": items[: payload.limit]}


class CreateFollowUpTool(BaseTool):
    name = "create_follow_up"
    description = "Create a draft application follow-up for an opportunity."
    args_model = CreateFollowUpArgs
    permission_scope = SCOPE_APPLICATION_WRITE
    side_effects = SideEffect.INTERNAL_WRITE

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = CreateFollowUpArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        application = Application(
            user_id=ctx.user_id,
            opportunity_id=opportunity.id,
            status=ApplicationStatus.DRAFT,
            notes=payload.notes or None,
            artifacts={"follow_up_created_at": datetime.now(UTC).isoformat()},
        )
        ctx.session.add(application)
        await ctx.session.flush()
        return {
            "application_id": str(application.id),
            "opportunity_id": str(opportunity.id),
            "status": application.status.value,
        }


class PrepareApplicationTool(BaseTool):
    name = "prepare_application"
    description = "Store an internal application checklist draft."
    args_model = PrepareApplicationArgs
    permission_scope = SCOPE_APPLICATION_WRITE
    side_effects = SideEffect.INTERNAL_WRITE

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = PrepareApplicationArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        application = Application(
            user_id=ctx.user_id,
            opportunity_id=opportunity.id,
            status=ApplicationStatus.DRAFT,
            artifacts={
                "checklist": payload.checklist,
                "prepared_at": datetime.now(UTC).isoformat(),
            },
        )
        ctx.session.add(application)
        await ctx.session.flush()
        return {
            "application_id": str(application.id),
            "checklist": payload.checklist,
            "status": application.status.value,
        }


class GenerateOutreachTool(BaseTool):
    name = "generate_outreach"
    description = "Draft outreach copy; sending requires external approval."
    args_model = GenerateOutreachArgs
    permission_scope = SCOPE_EXTERNAL_COMMUNICATE
    side_effects = SideEffect.EXTERNAL
    max_calls_per_run = 5

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = GenerateOutreachArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        draft = (
            f"Subject: Interest in {opportunity.title}\n\n"
            f"Hello,\n\n"
            f"I am writing to express interest in the {opportunity.title} "
            f"opportunity at {opportunity.organization_name or 'your organisation'}. "
            f"My background aligns with the role requirements.\n\n"
            f"Best regards"
        )
        return {
            "opportunity_id": str(opportunity.id),
            "channel": payload.channel,
            "tone": payload.tone,
            "draft": draft,
            "sent": False,
        }


class SaveOpportunityTool(BaseTool):
    name = "save_opportunity"
    description = "Ingest a new opportunity from structured fields."
    args_model = SaveOpportunityArgs
    permission_scope = SCOPE_OPPORTUNITY_WRITE
    side_effects = SideEffect.INTERNAL_WRITE

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = SaveOpportunityArgs.model_validate(args)
        ingestion = IngestionService(ctx.session)
        result = await ingestion.ingest(
            RawOpportunity(
                title=payload.title,
                source_url=str(payload.source_url),
                category=payload.category,
                organization_name=payload.organization_name,
                description=payload.description,
            )
        )
        if result.opportunity is None:
            raise ValidationError(result.reason or "Ingestion rejected")
        return {
            "outcome": result.outcome.value,
            "opportunity_id": str(result.opportunity.id),
            "status": result.opportunity.status.value,
        }


class UpdateOpportunityStatusTool(BaseTool):
    name = "update_opportunity_status"
    description = "Transition an opportunity to a new lifecycle status."
    args_model = UpdateOpportunityStatusArgs
    permission_scope = SCOPE_OPPORTUNITY_WRITE
    side_effects = SideEffect.INTERNAL_WRITE

    async def run(self, args: BaseModel, ctx: ToolContext) -> dict[str, Any]:
        payload = UpdateOpportunityStatusArgs.model_validate(args)
        opportunity = await ctx.session.get(Opportunity, payload.opportunity_id)
        if opportunity is None:
            raise ToolNotFoundError("Opportunity not found")
        ingestion = IngestionService(ctx.session)
        await ingestion.set_status(
            opportunity,
            payload.status,
            reason=payload.reason or "tool_update",
        )
        return {
            "opportunity_id": str(opportunity.id),
            "status": opportunity.status.value,
        }


NATIVE_TOOLS: tuple[type[BaseTool], ...] = (
    SearchOpportunitiesTool,
    SearchWebTool,
    ResearchCompanyTool,
    GetCompanyInformationTool,
    ExtractDeadlineTool,
    CheckEligibilityTool,
    SearchUserProfileTool,
    SearchUserDocumentsTool,
    CalculateOpportunityScoreTool,
    GetPreviousOpportunitiesTool,
    CreateFollowUpTool,
    PrepareApplicationTool,
    GenerateOutreachTool,
    SaveOpportunityTool,
    UpdateOpportunityStatusTool,
)
