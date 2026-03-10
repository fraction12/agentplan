"""Shared data models/types for agentplan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


RowLike = Mapping[str, Any]


@dataclass(frozen=True)
class Project:
    id: int
    slug: str
    title: str
    status: str
    notes: Optional[str]
    dir: Optional[str]
    timeout_sec: Optional[int]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: RowLike) -> "Project":
        return cls(
            id=int(row["id"]),
            slug=str(row["slug"]),
            title=str(row["title"]),
            status=str(row["status"]),
            notes=row["notes"],
            dir=row["dir"] if "dir" in row else None,
            timeout_sec=row["timeout_sec"] if "timeout_sec" in row else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


@dataclass(frozen=True)
class Ticket:
    id: int
    project_id: int
    num: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    tags: str
    depends_on: str
    notes: Optional[str]
    started_by: Optional[str]
    done_by: Optional[str]
    due_date: Optional[str]
    claimed_at: Optional[str]
    claim_timeout: Optional[int]
    timeout_sec: Optional[int]
    created_at: str
    completed_at: Optional[str]
    close_note: Optional[str] = None
    model_tier: str = "auto"

    @classmethod
    def from_row(cls, row: RowLike) -> "Ticket":
        return cls(
            id=int(row["id"]),
            project_id=int(row["project_id"]),
            num=int(row["num"]),
            title=str(row["title"]),
            description=row["description"],
            status=str(row["status"]),
            priority=str(row["priority"]),
            tags=str(row["tags"]),
            depends_on=str(row["depends_on"]),
            notes=row["notes"],
            started_by=row["started_by"],
            done_by=row["done_by"],
            due_date=row["due_date"],
            claimed_at=row["claimed_at"] if "claimed_at" in row else None,
            claim_timeout=row["claim_timeout"] if "claim_timeout" in row else None,
            timeout_sec=row["timeout_sec"] if "timeout_sec" in row else None,
            created_at=str(row["created_at"]),
            completed_at=row["completed_at"],
            close_note=row["close_note"] if "close_note" in row else None,
            model_tier=row["model_tier"] if "model_tier" in row else "auto",
        )


@dataclass(frozen=True)
class Subtask:
    id: int
    ticket_id: int
    num: int
    title: str
    status: str
    created_at: str
    completed_at: Optional[str]

    @classmethod
    def from_row(cls, row: RowLike) -> "Subtask":
        return cls(
            id=int(row["id"]),
            ticket_id=int(row["ticket_id"]),
            num=int(row["num"]),
            title=str(row["title"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            completed_at=row["completed_at"],
        )


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    ticket_id: int
    old_state: Optional[str]
    new_state: str
    changed_at: str

    @classmethod
    def from_row(cls, row: RowLike) -> "HistoryEntry":
        return cls(
            id=int(row["id"]),
            ticket_id=int(row["ticket_id"]),
            old_state=row["old_state"],
            new_state=str(row["new_state"]),
            changed_at=str(row["changed_at"]),
        )


@dataclass(frozen=True)
class Role:
    id: int
    name: str
    description: Optional[str]
    created_at: str

    @classmethod
    def from_row(cls, row: RowLike) -> "Role":
        return cls(
            id=int(row["id"]),
            name=str(row["name"]),
            description=row["description"],
            created_at=str(row["created_at"]),
        )


__all__ = ["Project", "Ticket", "Subtask", "HistoryEntry", "Role", "RowLike"]
