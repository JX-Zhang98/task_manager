import json

from app.cli import main


def run_cli(capsys, data_file, *args):
    exit_code = main(["--file", str(data_file), *args])
    output = capsys.readouterr().out
    return exit_code, json.loads(output)


def test_cli_add_update_list_and_archive_flow(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"

    exit_code, payload = run_cli(
        capsys,
        data_file,
        "add",
        "CLI task",
        "--description",
        "Created from CLI",
        "--quadrant",
        "q1",
        "--due-date",
        "2026-06-09T09:30",
        "--has-time",
        "--reminder-minutes",
        "5",
    )
    assert exit_code == 0
    task_id = payload["task_id"]
    assert payload["changed"]
    assert payload["events"][0]["type"] == "TaskChanged"

    exit_code, payload = run_cli(capsys, data_file, "list", "--view", "matrix")
    assert exit_code == 0
    assert [task["id"] for task in payload["data"]["tasks"]] == [task_id]

    exit_code, payload = run_cli(
        capsys,
        data_file,
        "update",
        task_id,
        "--title",
        "Updated CLI task",
        "--clear-due-date",
    )
    assert exit_code == 0
    assert payload["changed"]

    exit_code, payload = run_cli(capsys, data_file, "get", task_id)
    assert exit_code == 0
    assert payload["data"]["task"]["title"] == "Updated CLI task"
    assert payload["data"]["task"]["due_date"] is None

    exit_code, _ = run_cli(
        capsys,
        data_file,
        "complete",
        task_id,
        "--completed-at",
        "2026-06-07T10:00:00",
    )
    assert exit_code == 0

    exit_code, payload = run_cli(capsys, data_file, "list", "--view", "archive")
    assert exit_code == 0
    assert [task["id"] for task in payload["data"]["tasks"]] == [task_id]
    audit_file = data_file.parent / "audit.log.jsonl"
    audit_records = [
        json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["command"] for record in audit_records] == [
        "AddTask",
        "UpdateTask",
        "CompleteTask",
    ]


def test_cli_check_reminders_outputs_events(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    _, add_payload = run_cli(
        capsys,
        data_file,
        "add",
        "Reminder",
        "--due-date",
        "2026-06-08T10:00:00",
        "--has-time",
        "--reminder-minutes",
        "30",
    )
    task_id = add_payload["task_id"]

    exit_code, payload = run_cli(
        capsys,
        data_file,
        "check-reminders",
        "--now",
        "2026-06-08T09:30:00",
    )

    assert exit_code == 0
    assert payload["changed"]
    assert payload["data"]["reminders"] == [{"task_id": task_id, "title": "Reminder"}]
    assert [event["type"] for event in payload["events"]] == [
        "ReminderTriggered",
        "TaskChanged",
    ]


def test_cli_returns_failure_for_invalid_command_data(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"

    exit_code, payload = run_cli(capsys, data_file, "add", "Title", "--quadrant", "bad")

    assert exit_code == 1
    assert not payload["ok"]
    assert payload["message"] == "Invalid quadrant"

    exit_code, payload = run_cli(capsys, data_file, "check-reminders", "--now", "bad")

    assert exit_code == 1
    assert not payload["ok"]
    assert payload["message"] == "Invalid datetime"


def test_cli_delete_requires_confirm_or_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    _, add_payload = run_cli(capsys, data_file, "add", "Delete candidate")
    task_id = add_payload["task_id"]

    exit_code, payload = run_cli(capsys, data_file, "delete", task_id)

    assert exit_code == 1
    assert payload["message"] == "Delete requires --confirm or --dry-run"

    exit_code, payload = run_cli(capsys, data_file, "delete", task_id, "--dry-run")

    assert exit_code == 0
    assert payload["would_change"]
    assert payload["preview"]["operation"] == "delete"

    exit_code, payload = run_cli(capsys, data_file, "get", task_id)
    assert exit_code == 0
    assert payload["data"]["task"]["id"] == task_id

    exit_code, payload = run_cli(capsys, data_file, "delete", task_id, "--confirm")

    assert exit_code == 0
    assert payload["changed"]


def test_cli_future_ai_delete_must_be_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    _, add_payload = run_cli(capsys, data_file, "add", "AI delete candidate")
    task_id = add_payload["task_id"]

    exit_code, payload = run_cli(
        capsys,
        data_file,
        "--source",
        "future_ai",
        "delete",
        task_id,
        "--confirm",
    )

    assert exit_code == 1
    assert payload["message"] == "future_ai delete requires dry-run"

    exit_code, payload = run_cli(
        capsys,
        data_file,
        "--source",
        "future_ai",
        "delete",
        task_id,
        "--dry-run",
    )

    assert exit_code == 0
    assert payload["would_change"]


def test_cli_adds_lists_and_filters_tags(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    _, first_payload = run_cli(
        capsys,
        data_file,
        "add",
        "Tagged task",
        "--tag",
        "Work",
        "--tag",
        "Deep",
    )
    first_id = first_payload["task_id"]
    _, second_payload = run_cli(capsys, data_file, "add", "Other task", "--tag", "Home")
    second_id = second_payload["task_id"]

    exit_code, payload = run_cli(capsys, data_file, "tags")

    assert exit_code == 0
    assert [(tag["name"], tag["count"]) for tag in payload["data"]["tags"]] == [
        ("Deep", 1),
        ("Home", 1),
        ("Work", 1),
    ]

    exit_code, payload = run_cli(capsys, data_file, "list", "--tag", "Work")

    assert exit_code == 0
    assert [task["id"] for task in payload["data"]["tasks"]] == [first_id]
    assert payload["data"]["tag"] == "Work"

    exit_code, payload = run_cli(capsys, data_file, "list", "--tag", "Home")

    assert exit_code == 0
    assert [task["id"] for task in payload["data"]["tasks"]] == [second_id]


def test_cli_reuses_existing_tag_color(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    _, first_payload = run_cli(capsys, data_file, "add", "First", "--tag", "Work")
    first_id = first_payload["task_id"]
    _, second_payload = run_cli(capsys, data_file, "add", "Second", "--tag", "Work")
    second_id = second_payload["task_id"]

    _, first = run_cli(capsys, data_file, "get", first_id)
    _, second = run_cli(capsys, data_file, "get", second_id)

    assert first["data"]["task"]["tags"][0]["color"] == second["data"]["task"]["tags"][0]["color"]


# ── Tag management CLI tests ──────────────────────────────────────


def test_cli_tag_rename_requires_confirm_or_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-rename", "Work", "Deep Work")

    assert exit_code == 1
    assert payload["message"] == "tag-rename requires --confirm or --dry-run"


def test_cli_tag_rename_renames_across_tasks(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "First", "--tag", "Work")
    run_cli(capsys, data_file, "add", "Second", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-rename", "Work", "Deep Work", "--confirm")

    assert exit_code == 0
    assert payload["changed"]
    assert payload["data"]["affected_task_count"] == 2

    # Verify tasks updated
    _, list_payload = run_cli(capsys, data_file, "list", "--tag", "Deep Work")
    assert len(list_payload["data"]["tasks"]) == 2


def test_cli_tag_delete_requires_confirm_or_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-delete", "Work")

    assert exit_code == 1
    assert payload["message"] == "tag-delete requires --confirm or --dry-run"


def test_cli_tag_delete_removes_from_all_tasks(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "First", "--tag", "Work")
    run_cli(capsys, data_file, "add", "Second", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-delete", "Work", "--confirm")

    assert exit_code == 0
    assert payload["changed"]

    # Verify tag removed
    _, tags_payload = run_cli(capsys, data_file, "tags")
    tag_names = [t["name"] for t in tags_payload["data"]["tags"]]
    assert "Work" not in tag_names


def test_cli_tag_delete_dry_run_previews(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-delete", "Work", "--dry-run")

    assert exit_code == 0
    assert not payload["changed"]
    assert payload["would_change"]
    assert payload["preview"]["operation"] == "delete_tag"

    # Verify tag still exists
    _, tags_payload = run_cli(capsys, data_file, "tags")
    assert any(t["name"] == "Work" for t in tags_payload["data"]["tags"])


def test_cli_tag_merge_requires_confirm_or_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-merge", "Work", "Home")

    assert exit_code == 1
    assert payload["message"] == "tag-merge requires --confirm or --dry-run"


def test_cli_tag_merge_replaces_source_with_target(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "First", "--tag", "Work")
    run_cli(capsys, data_file, "add", "Second", "--tag", "Work", "--tag", "Home")

    exit_code, payload = run_cli(capsys, data_file, "tag-merge", "Work", "Home", "--confirm")

    assert exit_code == 0
    assert payload["changed"]

    # Verify all tasks have Home tag, no Work
    _, list_payload = run_cli(capsys, data_file, "list", "--tag", "Home")
    assert len(list_payload["data"]["tasks"]) == 2


def test_cli_tag_prune_requires_confirm_or_dry_run(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-prune")

    assert exit_code == 1
    assert payload["message"] == "tag-prune requires --confirm or --dry-run"


def test_cli_tag_prune_removes_stale_tags(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Active", "--tag", "ActiveTag")

    exit_code, payload = run_cli(capsys, data_file, "tag-prune", "--confirm")

    assert exit_code == 0
    assert payload["data"]["stale_count"] == 0  # Active tag is not stale


def test_cli_tag_prune_dry_run_previews(tmp_path, capsys):
    data_file = tmp_path / "tasks.json"
    run_cli(capsys, data_file, "add", "Task", "--tag", "Work")

    exit_code, payload = run_cli(capsys, data_file, "tag-prune", "--dry-run")

    assert exit_code == 0
    assert not payload["changed"]
