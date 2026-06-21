from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class TaskChanged:
    action: str
    task_id: Optional[str] = None


@dataclass(frozen=True)
class ReminderTriggered:
    task_id: str
    title: str


@dataclass(frozen=True)
class TagChanged:
    action: str
    tag_name: Optional[str] = None
    affected_task_count: int = 0


ApplicationEvent = Union[TaskChanged, ReminderTriggered, TagChanged]
