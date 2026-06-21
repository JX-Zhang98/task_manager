from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.application.commands import (
    AddTask,
    CheckReminders,
    CompleteTask,
    DeleteTag,
    DeleteTask,
    MergeTag,
    MoveTask,
    PruneStaleTags,
    RenameTag,
    ReopenTask,
    UpdateTask,
)
from app.application.context import CommandContext
from app.application.event_bus import EventBus
from app.application.events import ReminderTriggered, TaskChanged
from app.application.task_app import TaskApplication
from app.config import DATA_DIR
from app.infrastructure.audit_log import JsonlAuditLog
from app.infrastructure.json_task_repository import JsonTaskRepository
from app.infrastructure.json_tag_catalog_repository import JsonTagCatalogRepository
from app.models.task import Task


class TaskService(QObject):
    data_changed = pyqtSignal()
    reminder_triggered = pyqtSignal(str, str)

    def __init__(self, filename: Optional[str] = None, enable_timer: bool = True):
        super().__init__()
        self.filepath = Path(filename) if filename else DATA_DIR / "tasks.json"
        self.repository = JsonTaskRepository(self.filepath)
        self.audit_log = JsonlAuditLog(self.filepath.parent / "audit.log.jsonl")
        self.tag_catalog_repo = JsonTagCatalogRepository(self.filepath.parent / "tags.json")
        self.context = CommandContext(source="ui")
        self.event_bus = EventBus()
        self.event_bus.subscribe(TaskChanged, self._handle_task_changed)
        self.event_bus.subscribe(ReminderTriggered, self._handle_reminder_triggered)
        self.application = TaskApplication(
            self.repository, self.event_bus, self.audit_log,
            tag_catalog_repository=self.tag_catalog_repo,
        )

        self.timer = None
        if enable_timer:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.check_reminders)
            self.timer.start(30_000)

    @property
    def tasks(self) -> dict[str, Task]:
        return self.application.tasks

    def load_data(self) -> None:
        self.application.reload()

    def save_data(self) -> None:
        self.application.save()
        self.data_changed.emit()

    def add_task(
        self,
        title: str,
        description: str = "",
        due_date: Optional[str] = None,
        has_time: bool = False,
        reminder_minutes: Optional[int] = None,
        quadrant: str = "inbox",
        tags: Optional[list[dict[str, str]]] = None,
    ) -> Task:
        result = self._dispatch(
            AddTask(
                title=title,
                description=description,
                due_date=due_date,
                has_time=has_time,
                reminder_minutes=reminder_minutes,
                quadrant=quadrant,
                tags=tags,
            )
        )
        task = self.get_task(result.task_id or "")
        if task is None:
            raise RuntimeError(result.message or "Task was not created")
        return task

    def update_task(
        self,
        task_id: str,
        title: str,
        description: str,
        due_date: Optional[str],
        has_time: bool,
        reminder_minutes: Optional[int],
        tags: Optional[list[dict[str, str]]] = None,
    ) -> None:
        self._dispatch(
            UpdateTask(
                task_id=task_id,
                title=title,
                description=description,
                due_date=due_date,
                has_time=has_time,
                reminder_minutes=reminder_minutes,
                tags=tags,
            )
        )

    def delete_task(self, task_id: str) -> None:
        self._dispatch(DeleteTask(task_id=task_id))

    def move_task(self, task_id: str, new_quadrant: str, insert_index: Optional[int] = None) -> None:
        self._dispatch(
            MoveTask(task_id=task_id, new_quadrant=new_quadrant, insert_index=insert_index)
        )

    def toggle_complete(
        self,
        task_id: str,
        completed: bool,
        completed_at: Optional[str] = None,
    ) -> None:
        if completed:
            self._dispatch(CompleteTask(task_id=task_id, completed_at=completed_at))
        else:
            self._dispatch(ReopenTask(task_id=task_id))

    def get_task(self, task_id: str) -> Task | None:
        return self.application.get_task(task_id)

    def get_visible_inbox_tasks(self) -> list[Task]:
        return self.application.get_visible_inbox_tasks()

    def get_visible_matrix_tasks(self) -> list[Task]:
        return self.application.get_visible_matrix_tasks()

    def get_archived_tasks(self) -> list[Task]:
        return self.application.get_archived_tasks()

    def visible_tasks_for_quadrant(self, quadrant: str) -> list[Task]:
        return self.application.visible_tasks_for_quadrant(quadrant)

    # ── Tag operations (thin dispatch wrappers) ───────────────────

    def get_all_tags(self) -> list[dict[str, str]]:
        return self.application.get_all_tags()

    def get_tag_reference_counts(self) -> dict[str, int]:
        return self.application.get_tag_reference_counts()

    def rename_tag(self, old_name: str, new_name: str, color: str) -> None:
        self._dispatch(RenameTag(old_name=old_name, new_name=new_name, color=color))

    def delete_tag(self, name: str) -> None:
        self._dispatch(DeleteTag(name=name))

    def merge_tag(self, source_name: str, target_tag: dict[str, str]) -> None:
        self._dispatch(
            MergeTag(
                source_name=source_name,
                target_name=target_tag["name"],
                target_color=target_tag.get("color", "#6B7280"),
            )
        )

    def prune_stale_tags(self) -> int:
        result = self._dispatch(PruneStaleTags())
        return result.data.get("stale_count", 0)

    def check_reminders(self) -> None:
        self._dispatch(CheckReminders())

    # ── Internal helpers ──────────────────────────────────────────

    def _dispatch(self, command):
        return self.application.dispatch(command, context=self.context)

    def _handle_task_changed(self, event) -> None:
        self.data_changed.emit()

    def _handle_reminder_triggered(self, event) -> None:
        self.reminder_triggered.emit(event.title, event.task_id)
