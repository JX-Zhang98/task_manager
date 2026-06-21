from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Union


@dataclass(frozen=True)
class AddTask:
    title: str
    description: str = ""
    due_date: Optional[str] = None
    has_time: bool = False
    reminder_minutes: Optional[int] = None
    quadrant: str = "inbox"
    tags: Optional[list[dict[str, str]]] = None


@dataclass(frozen=True)
class UpdateTask:
    task_id: str
    title: str
    description: str
    due_date: Optional[str]
    has_time: bool
    reminder_minutes: Optional[int]
    tags: Optional[list[dict[str, str]]] = None


@dataclass(frozen=True)
class DeleteTask:
    task_id: str


@dataclass(frozen=True)
class MoveTask:
    task_id: str
    new_quadrant: str
    insert_index: Optional[int] = None


@dataclass(frozen=True)
class CompleteTask:
    task_id: str
    completed_at: Optional[str] = None


@dataclass(frozen=True)
class ReopenTask:
    task_id: str


@dataclass(frozen=True)
class CheckReminders:
    now: Optional[datetime] = None


# ── Tag commands ──────────────────────────────────────────────────


@dataclass(frozen=True)
class RenameTag:
    old_name: str
    new_name: str
    color: str = "#6B7280"


@dataclass(frozen=True)
class DeleteTag:
    name: str


@dataclass(frozen=True)
class MergeTag:
    source_name: str
    target_name: str
    target_color: str = "#6B7280"


@dataclass(frozen=True)
class PruneStaleTags:
    cutoff_days: int = 90


TaskCommand = Union[
    AddTask,
    UpdateTask,
    DeleteTask,
    MoveTask,
    CompleteTask,
    ReopenTask,
    CheckReminders,
    RenameTag,
    DeleteTag,
    MergeTag,
    PruneStaleTags,
]
