"""SQLAlchemy models.

Importing this package registers every mapper on ``Base.metadata``, which is
what Alembic autogenerate and the test schema-drift check rely on. Keep the
``__all__`` list exhaustive.
"""

from app.db.base import Base
from app.models.agent_run import AgentRun, AgentTask, ToolCall
from app.models.application import Application, Outcome
from app.models.document import Document, DocumentChunk
from app.models.evaluation import EvaluationRun
from app.models.feedback import Feedback
from app.models.goal import Goal
from app.models.memory import MemoryRecord
from app.models.opportunity import (
    Opportunity,
    OpportunityEvent,
    OpportunityEvidence,
    OpportunityScore,
    OpportunitySource,
)
from app.models.user import User, UserProfile

__all__ = [
    "AgentRun",
    "AgentTask",
    "Application",
    "Base",
    "Document",
    "DocumentChunk",
    "EvaluationRun",
    "Feedback",
    "Goal",
    "MemoryRecord",
    "Opportunity",
    "OpportunityEvent",
    "OpportunityEvidence",
    "OpportunityScore",
    "OpportunitySource",
    "Outcome",
    "ToolCall",
    "User",
    "UserProfile",
]
