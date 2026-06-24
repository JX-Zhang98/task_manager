from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
from app.application.queries import ListTasks, list_tasks
from app.application.results import CommandResult
from app.application.serializers import command_result_to_dict, task_to_dict
from app.application.task_app import TaskApplication
from app.config import DATA_DIR, TAG_COLORS
from app.domain.task_rules import normalize_tags
from app.infrastructure.audit_log import JsonlAuditLog
from app.infrastructure.json_task_repository import JsonTaskRepository
from app.infrastructure.json_tag_catalog_repository import JsonTagCatalogRepository


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    application = build_application(args.file, args.audit_file)
    context = build_context(args)

    if args.command == "list":
        task_list = list_tasks(application, ListTasks(view=args.view))
        tasks = filter_tasks_by_tag(task_list.tasks, args.tag)
        return print_query_result(
            "Tasks listed",
            {
                "view": task_list.view,
                "tag": args.tag,
                "tasks": [task_to_dict(task) for task in tasks],
            },
            pretty=args.pretty,
        )
    if args.command == "tags":
        all_tags = application.get_all_tags()
        counts = application.get_tag_reference_counts()
        tags_with_counts = [
            {**tag, "count": counts.get(tag["name"].casefold(), 0)} for tag in all_tags
        ]
        return print_query_result(
            "Tags listed",
            {"tags": tags_with_counts},
            pretty=args.pretty,
        )
    if args.command == "get":
        task = application.get_task(args.task_id)
        if task is None:
            return print_result(
                CommandResult(ok=False, message="Task not found", task_id=args.task_id),
                pretty=args.pretty,
            )
        return print_query_result("Task loaded", {"task": task_to_dict(task)}, pretty=args.pretty)

    result = dispatch_command(application, args, context)
    return print_result(result, pretty=args.pretty)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TaskManager command line interface")
    parser.add_argument(
        "--file",
        default=str(DATA_DIR / "tasks.json"),
        help="Path to tasks JSON file. Defaults to data/tasks.json.",
    )
    parser.add_argument(
        "--audit-file",
        help="Path to audit JSONL file. Defaults to audit.log.jsonl next to --file.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--source", default="cli", help="Command source for audit records.")
    parser.add_argument("--request-id", help="Optional request id for audit records.")
    parser.add_argument("--actor", help="Optional actor for audit records.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument(
        "--view",
        choices=("all", "inbox", "matrix", "archive"),
        default="all",
        help="Task view to list.",
    )
    list_parser.add_argument("--tag", help="Only list tasks that have this tag.")

    subparsers.add_parser("tags", help="List all tags")

    get_parser = subparsers.add_parser("get", help="Get one task")
    get_parser.add_argument("task_id")

    add_parser = subparsers.add_parser("add", help="Add a task")
    add_parser.add_argument("title")
    add_parser.add_argument("--description", default="")
    add_parser.add_argument("--due-date")
    add_parser.add_argument("--has-time", action="store_true")
    add_parser.add_argument("--reminder-minutes", type=int)
    add_parser.add_argument("--quadrant", default="inbox")
    add_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Attach a tag to the new task. Can be repeated.",
    )
    add_execution_options(add_parser)

    update_parser = subparsers.add_parser("update", help="Update a task")
    update_parser.add_argument("task_id")
    update_parser.add_argument("--title")
    update_parser.add_argument("--description")
    update_parser.add_argument("--due-date")
    update_parser.add_argument("--clear-due-date", action="store_true")
    update_parser.add_argument("--has-time", action=argparse.BooleanOptionalAction)
    update_parser.add_argument("--reminder-minutes", type=int)
    update_parser.add_argument("--clear-reminder", action="store_true")
    add_execution_options(update_parser)

    move_parser = subparsers.add_parser("move", help="Move a task to another quadrant")
    move_parser.add_argument("task_id")
    move_parser.add_argument("quadrant")
    add_execution_options(move_parser)

    complete_parser = subparsers.add_parser("complete", help="Mark a task as completed")
    complete_parser.add_argument("task_id")
    complete_parser.add_argument("--completed-at")
    add_execution_options(complete_parser)

    reopen_parser = subparsers.add_parser("reopen", help="Reopen a completed task")
    reopen_parser.add_argument("task_id")
    add_execution_options(reopen_parser)

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("task_id")
    add_execution_options(delete_parser, confirm=True)

    reminders_parser = subparsers.add_parser("check-reminders", help="Trigger due reminders")
    reminders_parser.add_argument("--now")
    add_execution_options(reminders_parser)

    # ── Tag management subcommands ────────────────────────────────

    tag_rename_parser = subparsers.add_parser("tag-rename", help="Rename a tag across all tasks")
    tag_rename_parser.add_argument("old_name")
    tag_rename_parser.add_argument("new_name")
    tag_rename_parser.add_argument("--color", help="New color for the renamed tag")
    add_execution_options(tag_rename_parser, confirm=True)

    tag_delete_parser = subparsers.add_parser("tag-delete", help="Delete a tag from all tasks")
    tag_delete_parser.add_argument("name")
    add_execution_options(tag_delete_parser, confirm=True)

    tag_merge_parser = subparsers.add_parser("tag-merge", help="Merge one tag into another")
    tag_merge_parser.add_argument("source_name")
    tag_merge_parser.add_argument("target_name")
    add_execution_options(tag_merge_parser, confirm=True)

    tag_prune_parser = subparsers.add_parser("tag-prune", help="Remove unreferenced stale tags")
    tag_prune_parser.add_argument("--cutoff-days", type=int, default=90)
    add_execution_options(tag_prune_parser, confirm=True)

    return parser


def add_execution_options(parser: argparse.ArgumentParser, *, confirm: bool = False) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Preview without changing data.")
    if confirm:
        parser.add_argument("--confirm", action="store_true", help="Confirm destructive action.")


def build_application(filename: str, audit_file: str | None) -> TaskApplication:
    data_path = Path(filename)
    audit_path = Path(audit_file) if audit_file else data_path.parent / "audit.log.jsonl"
    tag_catalog_path = data_path.parent / "tags.json"
    return TaskApplication(
        JsonTaskRepository(data_path),
        audit_log=JsonlAuditLog(audit_path),
        tag_catalog_repository=JsonTagCatalogRepository(tag_catalog_path),
    )


def build_context(args: argparse.Namespace) -> CommandContext:
    return CommandContext(
        source=args.source,
        dry_run=getattr(args, "dry_run", False),
        request_id=args.request_id,
        actor=args.actor,
    )


def dispatch_command(
    application: TaskApplication,
    args: argparse.Namespace,
    context: CommandContext,
) -> CommandResult:
    if args.command == "add":
        return application.dispatch(
            AddTask(
                title=args.title,
                description=args.description,
                due_date=args.due_date,
                has_time=args.has_time,
                reminder_minutes=args.reminder_minutes,
                quadrant=args.quadrant,
                tags=build_tags(application, args.tag),
            ),
            context=context,
        )
    if args.command == "update":
        return dispatch_update(application, args, context)
    if args.command == "move":
        return application.dispatch(
            MoveTask(task_id=args.task_id, new_quadrant=args.quadrant),
            context=context,
        )
    if args.command == "complete":
        return application.dispatch(
            CompleteTask(task_id=args.task_id, completed_at=args.completed_at),
            context=context,
        )
    if args.command == "reopen":
        return application.dispatch(ReopenTask(task_id=args.task_id), context=context)
    if args.command == "delete":
        if not args.confirm and not context.dry_run:
            return CommandResult(
                ok=False,
                message="Delete requires --confirm or --dry-run",
                task_id=args.task_id,
            )
        return application.dispatch(DeleteTask(task_id=args.task_id), context=context)
    if args.command == "check-reminders":
        try:
            now = parse_datetime_arg(args.now)
        except ValueError:
            return CommandResult(ok=False, message="Invalid datetime")
        return application.dispatch(CheckReminders(now=now), context=context)

    # ── Tag management commands ───────────────────────────────────
    if args.command == "tag-rename":
        if not args.confirm and not context.dry_run:
            return CommandResult(ok=False, message="tag-rename requires --confirm or --dry-run")
        color = args.color or resolve_tag_color(application, args.new_name)
        return application.dispatch(
            RenameTag(old_name=args.old_name, new_name=args.new_name, color=color),
            context=context,
        )
    if args.command == "tag-delete":
        if not args.confirm and not context.dry_run:
            return CommandResult(ok=False, message="tag-delete requires --confirm or --dry-run")
        return application.dispatch(DeleteTag(name=args.name), context=context)
    if args.command == "tag-merge":
        if not args.confirm and not context.dry_run:
            return CommandResult(ok=False, message="tag-merge requires --confirm or --dry-run")
        target_color = resolve_tag_color(application, args.target_name)
        return application.dispatch(
            MergeTag(
                source_name=args.source_name,
                target_name=args.target_name,
                target_color=target_color,
            ),
            context=context,
        )
    if args.command == "tag-prune":
        if not args.confirm and not context.dry_run:
            return CommandResult(ok=False, message="tag-prune requires --confirm or --dry-run")
        return application.dispatch(
            PruneStaleTags(cutoff_days=args.cutoff_days),
            context=context,
        )

    return CommandResult(ok=False, message=f"Unsupported command: {args.command}")


def dispatch_update(
    application: TaskApplication,
    args: argparse.Namespace,
    context: CommandContext,
) -> CommandResult:
    task = application.get_task(args.task_id)
    if task is None:
        return CommandResult(ok=False, message="Task not found", task_id=args.task_id)

    due_date = task.due_date
    if args.clear_due_date:
        due_date = None
    elif args.due_date is not None:
        due_date = args.due_date

    reminder_minutes = task.reminder_minutes
    if args.clear_reminder:
        reminder_minutes = None
    elif args.reminder_minutes is not None:
        reminder_minutes = args.reminder_minutes
    has_time = args.has_time if args.has_time is not None else task.has_time
    if due_date is None:
        has_time = False

    return application.dispatch(
        UpdateTask(
            task_id=args.task_id,
            title=args.title if args.title is not None else task.title,
            description=args.description if args.description is not None else task.description,
            due_date=due_date,
            has_time=has_time,
            reminder_minutes=reminder_minutes if due_date else None,
        ),
        context=context,
    )


def parse_datetime_arg(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def filter_tasks_by_tag(tasks, tag_name: str | None):
    if not tag_name:
        return tasks
    key = tag_name.casefold()
    return [
        task for task in tasks if any(tag.get("name", "").casefold() == key for tag in task.tags)
    ]


def build_tags(application: TaskApplication, tag_names: list[str]) -> list[dict[str, str]]:
    """Construct tag dicts from CLI --tag arguments, resolving colors from the catalog."""
    existing = {tag["name"].casefold(): tag for tag in application.get_all_tags()}
    result: list[dict[str, str]] = []
    used = set(existing)
    for raw_name in tag_names:
        name = raw_name.strip()
        if not name:
            continue
        key = name.casefold()
        if any(tag["name"].casefold() == key for tag in result):
            continue
        if key in existing:
            result.append(existing[key])
            continue
        color = TAG_COLORS[len(used) % len(TAG_COLORS)]
        used.add(key)
        result.append({"name": name, "color": color})
    return normalize_tags(result)


def resolve_tag_color(application: TaskApplication, name: str) -> str:
    """Look up a tag's color from the catalog, defaulting to #6B7280."""
    for tag in application.get_all_tags():
        if tag["name"].casefold() == name.strip().casefold():
            return tag["color"]
    return "#6B7280"


def print_query_result(message: str, data: dict[str, Any], *, pretty: bool) -> int:
    return print_result(
        CommandResult(ok=True, message=message, changed=False, data=data),
        pretty=pretty,
    )


def print_result(result: CommandResult, *, pretty: bool) -> int:
    indent = 2 if pretty else None
    json.dump(command_result_to_dict(result), sys.stdout, ensure_ascii=False, indent=indent)
    sys.stdout.write("\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
