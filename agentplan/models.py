"""Shared data models/types for agentplan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


RowLike = Mapping[str, Any]


@dataclass(frozen=True)
class Space:
    id: int
    slug: str
    title: str
    description: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: RowLike) -> "Space":
        return cls(
            id=int(row["id"]),
            slug=row["slug"],
            title=row["title"],
            description=row["description"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


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
            slug=row["slug"],
            title=row["title"],
            status=row["status"],
            notes=row["notes"],
            dir=row.get("dir"),
            timeout_sec=row.get("timeout_sec"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
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
            title=row["title"],
            description=row["description"],
            status=row["status"],
            priority=row["priority"],
            tags=row["tags"],
            depends_on=row["depends_on"],
            notes=row["notes"],
            started_by=row["started_by"],
            done_by=row["done_by"],
            due_date=row["due_date"],
            claimed_at=row.get("claimed_at"),
            claim_timeout=row.get("claim_timeout"),
            timeout_sec=row.get("timeout_sec"),
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            close_note=row.get("close_note"),
            model_tier=row.get("model_tier", "auto"),
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
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
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
            new_state=row["new_state"],
            changed_at=row["changed_at"],
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
            name=row["name"],
            description=row["description"],
            created_at=row["created_at"],
        )


__all__ = ["Space", "Project", "Ticket", "Subtask", "HistoryEntry", "Role", "RowLike"]
