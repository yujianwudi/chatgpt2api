"""Durable memory-operation scopes and outcomes; never stores credentials."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Integer, JSON, String, delete, select, update
from sqlalchemy.orm import sessionmaker

from services.application_database import DatabaseBase, initialize_application_database, resolve_database_url


class MemoryOperationModel(DatabaseBase):
    __tablename__ = "memory_operations"

    id = Column(String(64), primary_key=True)
    payload = Column(JSON, nullable=False)
    event_sequence = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, index=True)


class MemoryOperationOutcomeModel(DatabaseBase):
    __tablename__ = "memory_operation_outcomes"

    job_id = Column(String(64), primary_key=True)
    account_id = Column(String(64), primary_key=True)
    status = Column(String(16), nullable=False, index=True)
    message = Column(String(500), nullable=False)
    sequence = Column(Integer, nullable=False, default=0)


class MemoryOperationRepository:
    """Persist frozen management IDs and per-account result metadata for 7 days."""

    def __init__(self, database_url: str | None = None) -> None:
        self.engine = initialize_application_database(database_url or resolve_database_url())
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create(self, job_id: str, action: str, target_ids: list[str], missing_ids: list[str]) -> None:
        ids = list(dict.fromkeys([*target_ids, *missing_ids]))
        payload = {"action": action, "target_ids": ids}
        missing_sequence = {aid: i + 1 for i, aid in enumerate(dict.fromkeys(missing_ids))}
        with self.Session.begin() as session:
            session.add(MemoryOperationModel(
                id=job_id, payload=payload, event_sequence=len(missing_sequence),
                updated_at=datetime.now(timezone.utc),
            ))
            missing = set(missing_ids)
            session.add_all([MemoryOperationOutcomeModel(
                job_id=job_id, account_id=aid, status="failed" if aid in missing else "queued",
                message="账号不存在" if aid in missing else "", sequence=missing_sequence.get(aid, 0),
            ) for aid in ids])

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.Session() as session:
            row = session.get(MemoryOperationModel, job_id)
            if row is None:
                return None
            outcomes = session.execute(select(MemoryOperationOutcomeModel).where(
                MemoryOperationOutcomeModel.job_id == job_id,
            ).order_by(MemoryOperationOutcomeModel.sequence)).scalars().all()
            return {"id": job_id, **deepcopy(row.payload), "outcomes": {
                item.account_id: {"status": item.status, "message": item.message, "sequence": item.sequence} for item in outcomes
            }}

    def record(self, job_id: str, account_id: str, status: str, message: str = "") -> None:
        if status not in {"running", "confirmed", "pending", "failed", "skipped"}:
            raise ValueError("unsupported memory outcome")
        with self.Session.begin() as session:
            sequence = session.execute(update(MemoryOperationModel).where(MemoryOperationModel.id == job_id).values(
                updated_at=datetime.now(timezone.utc), event_sequence=MemoryOperationModel.event_sequence + 1,
            ).returning(MemoryOperationModel.event_sequence)).scalar_one_or_none()
            if sequence is None:
                return
            session.execute(update(MemoryOperationOutcomeModel).where(
                MemoryOperationOutcomeModel.job_id == job_id,
                MemoryOperationOutcomeModel.account_id == account_id,
            ).values(status=status, message=str(message)[:500], sequence=sequence))

    def pending(self) -> list[dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        with self.Session.begin() as session:
            expired = select(MemoryOperationModel.id).where(MemoryOperationModel.updated_at < cutoff)
            session.execute(delete(MemoryOperationOutcomeModel).where(MemoryOperationOutcomeModel.job_id.in_(expired)))
            session.execute(delete(MemoryOperationModel).where(MemoryOperationModel.updated_at < cutoff))
            unfinished = select(MemoryOperationOutcomeModel.job_id).where(
                MemoryOperationOutcomeModel.status.in_(("queued", "running", "pending")),
            )
            ids = session.execute(select(MemoryOperationModel.id).where(
                MemoryOperationModel.id.in_(unfinished),
            ).order_by(MemoryOperationModel.updated_at).limit(50)).scalars().all()
        return [job for job_id in ids if (job := self.get(job_id)) is not None]
