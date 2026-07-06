from datetime import datetime

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
from app.application.task_app import TITLE_MAX_LENGTH, TaskApplication
from app.models.task import Task


class InMemoryTaskRepository:
    def __init__(self, tasks=None):
        self.loaded_tasks = tasks or {}
        self.saved_tasks = {}
        self.save_count = 0

    def load_all(self):
        return dict(self.loaded_tasks)

    def save_all(self, tasks):
        self.saved_tasks = dict(tasks)
        self.save_count += 1


class InMemoryTagCatalogRepository:
    def __init__(self):
        self.catalog: list[dict[str, str]] = []
        self.save_count = 0

    def load_catalog(self):
        return list(self.catalog)

    def save_catalog(self, tags):
        self.catalog = list(tags)
        self.save_count += 1


class InMemoryAuditLog:
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(record)


def make_application(tasks=None, audit_log=None, tag_catalog=None):
    repository = InMemoryTaskRepository(tasks)
    event_bus = EventBus()
    events = []
    event_bus.subscribe(TaskChanged, events.append)
    event_bus.subscribe(ReminderTriggered, events.append)
    tag_repo = tag_catalog or InMemoryTagCatalogRepository()
    return (
        TaskApplication(repository, event_bus, audit_log, tag_catalog_repository=tag_repo),
        repository,
        events,
    )


def task_changed_events(events):
    return [event for event in events if isinstance(event, TaskChanged)]


def test_task_application_dispatches_task_lifecycle_commands():
    app, repository, events = make_application()

    add_result = app.dispatch(AddTask(title="Task", description="Desc"))
    task_id = add_result.task_id
    assert add_result.ok
    assert add_result.changed
    assert task_id
    assert app.get_task(task_id).title == "Task"

    update_result = app.dispatch(
        UpdateTask(
            task_id=task_id,
            title="Updated",
            description="New desc",
            due_date="2026-06-09T09:30",
            has_time=True,
            reminder_minutes=15,
        )
    )
    assert update_result.ok
    assert app.get_task(task_id).title == "Updated"
    assert app.get_task(task_id).reminder_minutes == 15

    move_result = app.dispatch(MoveTask(task_id=task_id, new_quadrant="q1"))
    assert move_result.ok
    assert app.get_task(task_id).quadrant == "q1"

    complete_result = app.dispatch(
        CompleteTask(task_id=task_id, completed_at="2026-06-08T10:00:00")
    )
    assert complete_result.ok
    assert app.get_task(task_id).completed
    assert app.get_task(task_id).completed_at == "2026-06-08T10:00:00"

    reopen_result = app.dispatch(ReopenTask(task_id=task_id))
    assert reopen_result.ok
    assert not app.get_task(task_id).completed
    assert app.get_task(task_id).completed_at is None

    delete_result = app.dispatch(DeleteTask(task_id=task_id))
    assert delete_result.ok
    assert app.get_task(task_id) is None

    assert repository.save_count == 6
    assert [event.action for event in task_changed_events(events)] == [
        "add",
        "update",
        "move",
        "complete",
        "reopen",
        "delete",
    ]


def test_task_application_adds_and_updates_tags():
    app, repository, events = make_application()

    add_result = app.dispatch(AddTask(title="Tagged", tags=[{"name": "Work", "color": "#2563EB"}]))
    task_id = add_result.task_id

    assert add_result.ok
    assert app.get_task(task_id).tags == [{"name": "Work", "color": "#2563EB"}]

    update_result = app.dispatch(
        UpdateTask(
            task_id=task_id,
            title="Tagged",
            description="",
            due_date=None,
            has_time=False,
            reminder_minutes=None,
            tags=[{"name": "Home", "color": "#059669"}],
        )
    )

    assert update_result.ok
    assert app.get_task(task_id).tags == [{"name": "Home", "color": "#059669"}]


def test_task_application_check_reminders_triggers_events():
    task = Task.create(
        title="Reminder",
        due_date="2026-06-08T10:00:00",
        has_time=True,
        reminder_minutes=30,
    )
    app, repository, events = make_application({task.id: task})

    result = app.dispatch(CheckReminders(now=datetime(2026, 6, 8, 9, 30)))

    assert result.ok
    assert result.changed
    assert repository.save_count == 1
    assert app.get_task(task.id).reminder_sent
    assert any(
        isinstance(event, ReminderTriggered) and event.task_id == task.id for event in events
    )
    assert task_changed_events(events)[-1].action == "check_reminders"


def test_task_application_validates_title_and_quadrant():
    app, repository, events = make_application()

    empty_title = app.dispatch(AddTask(title="   "))
    invalid_quadrant = app.dispatch(AddTask(title="Task", quadrant="bad"))

    assert not empty_title.ok
    assert empty_title.message == "Task title is required"
    assert not invalid_quadrant.ok
    assert invalid_quadrant.message == "Invalid quadrant"
    assert repository.save_count == 0
    assert events == []


def test_task_application_validates_dates_lengths_and_reminders():
    app, repository, events = make_application()

    bad_due_date = app.dispatch(AddTask(title="Task", due_date="bad"))
    bad_reminder = app.dispatch(
        AddTask(title="Task", due_date="2026-06-09T09:30:00", reminder_minutes=-1)
    )
    missing_due_date = app.dispatch(AddTask(title="Task", reminder_minutes=5))
    long_title = app.dispatch(AddTask(title="x" * (TITLE_MAX_LENGTH + 1)))
    task = app.dispatch(AddTask(title="Task"))
    bad_completed_at = app.dispatch(CompleteTask(task_id=task.task_id, completed_at="not-a-date"))

    assert bad_due_date.message == "Invalid due_date"
    assert bad_reminder.message == "reminder_minutes must be non-negative"
    assert missing_due_date.message == "reminder_minutes requires due_date"
    assert long_title.message == "Task title is too long"
    assert bad_completed_at.message == "Invalid completed_at"
    assert repository.save_count == 1
    assert [event.action for event in task_changed_events(events)] == ["add"]


def test_task_application_dry_run_delete_previews_without_changing_or_publishing_events():
    task = Task.create(title="Delete me")
    audit_log = InMemoryAuditLog()
    app, repository, events = make_application({task.id: task}, audit_log)

    result = app.dispatch(
        DeleteTask(task_id=task.id),
        context=CommandContext(source="future_ai", dry_run=True, request_id="req-1"),
    )

    assert result.ok
    assert not result.changed
    assert result.would_change
    assert result.preview["operation"] == "delete"
    assert app.get_task(task.id) is not None
    assert repository.save_count == 0
    assert events == []
    assert audit_log.records[0]["source"] == "future_ai"
    assert audit_log.records[0]["dry_run"]
    assert audit_log.records[0]["command"] == "DeleteTask"
    assert audit_log.records[0]["would_change"]


def test_task_application_rejects_future_ai_delete_without_dry_run():
    task = Task.create(title="Delete me")
    audit_log = InMemoryAuditLog()
    app, repository, events = make_application({task.id: task}, audit_log)

    result = app.dispatch(
        DeleteTask(task_id=task.id),
        context=CommandContext(source="future_ai"),
    )

    assert not result.ok
    assert result.message == "future_ai delete requires dry-run"
    assert app.get_task(task.id) is not None
    assert repository.save_count == 0
    assert events == []
    assert audit_log.records[0]["ok"] is False


# ── Tag command tests ──────────────────────────────────────────────


def test_task_application_renames_tag_across_tasks():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    app.dispatch(AddTask(title="First", tags=[work]))
    app.dispatch(AddTask(title="Second", tags=[work, home]))

    result = app.dispatch(RenameTag(old_name="Work", new_name="Deep Work", color="#7C3AED"))

    assert result.ok
    assert result.changed
    assert result.data["affected_task_count"] == 2

    # Verify tasks updated
    tasks = list(app.tasks.values())
    first_tags = tasks[0].tags
    second_tags = tasks[1].tags
    assert first_tags == [{"name": "Deep Work", "color": "#7C3AED"}]
    assert {"name": "Deep Work", "color": "#7C3AED"} in second_tags
    assert {"name": "Home", "color": "#059669"} in second_tags

    # Verify catalog updated
    catalog = app.tag_catalog_repository.load_catalog()
    assert any(t["name"] == "Deep Work" for t in catalog)

    # Verify TaskChanged event for rename_tag
    tag_events = task_changed_events(events)
    assert tag_events[-1].action == "rename_tag"


def test_task_application_deletes_tag_from_all_tasks():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    app.dispatch(AddTask(title="First", tags=[work]))
    app.dispatch(AddTask(title="Second", tags=[work, home]))

    result = app.dispatch(DeleteTag(name="Work"))

    assert result.ok
    assert result.changed
    assert result.data["affected_task_count"] == 2

    # Verify tag removed from tasks
    tasks = list(app.tasks.values())
    assert tasks[0].tags == []
    assert tasks[1].tags == [{"name": "Home", "color": "#059669"}]

    # Verify catalog updated
    catalog = app.tag_catalog_repository.load_catalog()
    assert not any(t["name"].casefold() == "work" for t in catalog)

    # Verify TaskChanged event for delete_tag
    tag_events = task_changed_events(events)
    assert tag_events[-1].action == "delete_tag"


def test_task_application_merges_tag():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    app.dispatch(AddTask(title="First", tags=[work]))
    app.dispatch(AddTask(title="Second", tags=[work, home]))

    result = app.dispatch(MergeTag(source_name="Work", target_name="Home", target_color="#059669"))

    assert result.ok
    assert result.changed
    assert result.data["affected_task_count"] == 2

    # Verify source replaced by target, no duplicates
    tasks = list(app.tasks.values())
    assert tasks[0].tags == [{"name": "Home", "color": "#059669"}]
    assert tasks[1].tags == [{"name": "Home", "color": "#059669"}]

    # Verify TaskChanged event for merge_tag
    tag_events = task_changed_events(events)
    assert tag_events[-1].action == "merge_tag"


def test_task_application_prunes_stale_tags():
    app, repository, events = make_application()

    active = {"name": "Active", "color": "#2563EB"}
    recent = {"name": "Recent", "color": "#059669"}
    old = {"name": "Old", "color": "#D97706"}
    app.dispatch(AddTask(title="Active", tags=[active]))
    recent_task_result = app.dispatch(AddTask(title="Recent done", tags=[recent]))
    old_task_result = app.dispatch(AddTask(title="Old done", tags=[old]))

    # Complete recent and old tasks
    app.dispatch(
        CompleteTask(
            task_id=recent_task_result.task_id,
            completed_at=datetime.now().isoformat(timespec="seconds"),
        )
    )
    app.dispatch(CompleteTask(task_id=old_task_result.task_id, completed_at="2000-01-01T10:00:00"))

    # Clear events from prior dispatches
    events.clear()

    result = app.dispatch(PruneStaleTags(cutoff_days=90))

    assert result.ok
    assert result.changed
    assert result.data["stale_count"] == 1

    # Verify old tag removed from its task
    old_task = app.get_task(old_task_result.task_id)
    assert old_task.tags == []

    # Verify TaskChanged event for prune_stale_tags
    tag_events = task_changed_events(events)
    assert tag_events[-1].action == "prune_stale_tags"


def test_task_application_tag_dry_run_previews_without_changing():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    app.dispatch(AddTask(title="First", tags=[work]))

    # Clear events from prior dispatches
    events.clear()

    result = app.dispatch(
        DeleteTag(name="Work"),
        context=CommandContext(dry_run=True),
    )

    assert result.ok
    assert not result.changed
    assert result.would_change
    assert result.preview["operation"] == "delete_tag"
    assert result.preview["affected_task_count"] == 1

    # Verify no mutations
    task = list(app.tasks.values())[0]
    assert task.tags == [{"name": "Work", "color": "#2563EB"}]
    # Verify no events published in dry-run mode
    assert task_changed_events(events) == []


def test_task_application_tag_dry_run_rename_previews():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    app.dispatch(AddTask(title="First", tags=[work]))

    events.clear()

    result = app.dispatch(
        RenameTag(old_name="Work", new_name="Deep Work", color="#7C3AED"),
        context=CommandContext(dry_run=True),
    )

    assert result.ok
    assert not result.changed
    assert result.would_change
    assert result.preview["operation"] == "rename_tag"
    assert result.preview["affected_task_count"] == 1


def test_task_application_tag_dry_run_prune_previews():
    app, repository, events = make_application()

    active = {"name": "Active", "color": "#2563EB"}
    app.dispatch(AddTask(title="Active", tags=[active]))

    events.clear()

    result = app.dispatch(
        PruneStaleTags(cutoff_days=90),
        context=CommandContext(dry_run=True),
    )

    assert result.ok
    assert not result.changed
    assert result.preview["operation"] == "prune_stale_tags"


def test_task_application_rejects_future_ai_tag_delete_without_dry_run():
    app, repository, events = make_application()
    app.dispatch(AddTask(title="Task", tags=[{"name": "Work", "color": "#2563EB"}]))

    events.clear()

    result = app.dispatch(
        DeleteTag(name="Work"),
        context=CommandContext(source="future_ai"),
    )

    assert not result.ok
    assert result.message == "future_ai delete requires dry-run"


def test_task_application_tag_audit_logging():
    audit_log = InMemoryAuditLog()
    app, repository, events = make_application(audit_log=audit_log)

    app.dispatch(AddTask(title="Task", tags=[{"name": "Work", "color": "#2563EB"}]))
    app.dispatch(DeleteTag(name="Work"))

    # Verify audit records include tag commands
    assert audit_log.records[-1]["command"] == "DeleteTag"
    assert audit_log.records[-1]["ok"] is True
    assert audit_log.records[-1]["changed"] is True


def test_task_application_get_all_tags():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    app.dispatch(AddTask(title="First", tags=[work]))
    app.dispatch(AddTask(title="Second", tags=[work, home]))

    all_tags = app.get_all_tags()

    tag_names = [t["name"] for t in all_tags]
    assert "Work" in tag_names
    assert "Home" in tag_names


def test_task_application_get_tag_reference_counts():
    app, repository, events = make_application()

    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    app.dispatch(AddTask(title="First", tags=[work]))
    app.dispatch(AddTask(title="Second", tags=[work, home]))

    counts = app.get_tag_reference_counts()

    assert counts["work"] == 2
    assert counts["home"] == 1


def test_task_application_merge_tag_same_source_and_target():
    app, repository, events = make_application()

    result = app.dispatch(MergeTag(source_name="Work", target_name="Work", target_color="#6B7280"))

    assert result.ok
    assert not result.changed
    assert result.message == "Source and target are the same tag"


def test_task_application_rename_tag_empty_new_name():
    app, repository, events = make_application()

    result = app.dispatch(RenameTag(old_name="Work", new_name="   ", color="#6B7280"))

    assert not result.ok
    assert result.message == "Tag name is required"


def test_task_application_add_task_syncs_catalog():
    tag_repo = InMemoryTagCatalogRepository()
    app, repository, events = make_application(tag_catalog=tag_repo)

    app.dispatch(AddTask(title="Task", tags=[{"name": "NewTag", "color": "#2563EB"}]))

    catalog = tag_repo.load_catalog()
    assert any(t["name"] == "NewTag" for t in catalog)


def test_task_application_update_task_syncs_catalog():
    tag_repo = InMemoryTagCatalogRepository()
    app, repository, events = make_application(tag_catalog=tag_repo)

    add_result = app.dispatch(AddTask(title="Task"))
    app.dispatch(
        UpdateTask(
            task_id=add_result.task_id,
            title="Task",
            description="",
            due_date=None,
            has_time=False,
            reminder_minutes=None,
            tags=[{"name": "NewLabel", "color": "#059669"}],
        )
    )

    catalog = tag_repo.load_catalog()
    assert any(t["name"] == "NewLabel" for t in catalog)
