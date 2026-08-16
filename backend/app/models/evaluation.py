"""Evaluation run records.

Every architectural change is expected to produce a row here before it counts as
done. ``git_sha`` + ``dataset_version`` make a result reproducible; the metrics
document is compared against the previous baseline by the CI gate.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import EvaluationStatus, enum_column


class EvaluationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_dataset_name_created_at", "dataset_name", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    suite: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(40))

    status: Mapped[EvaluationStatus] = mapped_column(
        enum_column(EvaluationStatus, "evaluation_status"),
        default=EvaluationStatus.PENDING,
        nullable=False,
    )
    config: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
