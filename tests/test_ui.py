from PyQt6.QtWidgets import QFrame, QPushButton

from app.services.task_service import TaskService
from app.ui.components.task_card import DragScrollArea, TagPill, TaskCardWidget
from app.ui.components.task_dialog import DateTimePickerPopup, TaskDialog
from app.ui.main_window import MainWindow
from app.ui.views.archive_dialog import ArchiveDialog
from app.ui.views.matrix import MatrixView
from app.ui.views.sidebar import SidebarView
from app.ui.views.tag_manager_dialog import TagManagerDialog


def make_service(tmp_path):
    return TaskService(filename=str(tmp_path / "ui_tasks.json"), enable_timer=False)


def test_ui_smoke_workflow(tmp_path, qapp):
    service = make_service(tmp_path)
    task = service.add_task(
        title="Smoke test task with a long enough title to wrap inside the card width",
        description="Created by automated smoke test.",
        due_date="2026-06-09T09:30",
        has_time=True,
        reminder_minutes=5,
    )

    sidebar = SidebarView(service)
    sidebar.refresh()
    assert sidebar.inbox_list.count() == 1

    service.move_task(task.id, "q1")
    matrix = MatrixView(service)
    matrix.refresh()
    assert matrix.lists["q1"].count() == 1

    service.toggle_complete(task.id, True)
    archive = ArchiveDialog(service)
    archive.load_data()
    archive.adjust_layout()
    assert archive.list_widget.count() == 0

    historical_task = service.add_task("Historical done", quadrant="q2")
    service.toggle_complete(historical_task.id, True, completed_at="2026-06-07T10:00:00")
    archive.load_data()
    archive.adjust_layout()
    assert archive.list_widget.count() == 1

    archive.close()
    matrix.close()
    sidebar.close()


def test_tag_manager_dialog_lists_tags_and_sidebar_has_entry(tmp_path, qapp):
    service = make_service(tmp_path)
    service.add_task("Tagged", tags=[{"name": "Work", "color": "#2563EB"}])

    dialog = TagManagerDialog(service)
    assert dialog.list_widget.count() == 1

    sidebar = SidebarView(service)
    button_texts = [button.text() for button in sidebar.findChildren(QPushButton)]
    assert "标签管理" in button_texts

    sidebar.close()
    dialog.close()


def test_sidebar_inbox_list_uses_remaining_height(tmp_path, qapp):
    service = make_service(tmp_path)
    sidebar = SidebarView(service)
    sidebar.resize(300, 750)
    sidebar.show()
    qapp.processEvents()

    assert sidebar.layout().stretch(sidebar.layout().indexOf(sidebar.inbox_list)) == 1
    assert sidebar.inbox_list.height() > 400

    sidebar.close()


def test_size_grip_stays_in_bottom_right(qapp):
    window = MainWindow()
    window.show()
    window.resize(1100, 750)
    qapp.processEvents()

    assert window.size_grip.x() == window.width() - window.size_grip.width()
    assert window.size_grip.y() == window.height() - window.size_grip.height()

    window.resize(900, 640)
    qapp.processEvents()

    assert window.size_grip.x() == window.width() - window.size_grip.width()
    assert window.size_grip.y() == window.height() - window.size_grip.height()

    window.close()


def test_matrix_filters_by_double_clicked_tag(tmp_path, qapp):
    service = make_service(tmp_path)
    work = {"name": "Work", "color": "#2563EB"}
    home = {"name": "Home", "color": "#059669"}
    service.add_task("Work task", quadrant="q1", tags=[work])
    service.add_task("Home task", quadrant="q1", tags=[home])

    matrix = MatrixView(service)
    matrix.refresh()
    assert matrix.lists["q1"].count() == 2

    matrix.filter_by_tag("Work")
    assert matrix.lists["q1"].count() == 1

    matrix.filter_by_tag("Work")
    assert matrix.lists["q1"].count() == 2
    assert service.get_all_tags() == [home, work]

    matrix.close()


def test_matrix_filter_header_truncates_long_tag(tmp_path, qapp):
    service = make_service(tmp_path)
    long_tag = {"name": "ImportantLongTagName", "color": "#2563EB"}
    service.add_task("Tagged task", quadrant="q1", tags=[long_tag])

    matrix = MatrixView(service)
    matrix.filter_by_tag(long_tag["name"])

    assert matrix.headers["q1"].text().endswith("#Importan...")
    assert long_tag["name"] not in matrix.headers["q1"].text()
    assert matrix.headers["q1"].toolTip() == long_tag["name"]

    matrix.close()


def test_new_task_dialog_due_date_defaults(qapp):
    dialog = TaskDialog()

    assert dialog.has_date_check.isChecked()
    assert not dialog.has_time_check.isChecked()
    assert dialog.due_edit.isEnabled()
    assert dialog.due_edit.displayFormat() == "yyyy-MM-dd"

    dialog.close()


def test_date_time_picker_shows_time_panel_only_when_needed(qapp):
    dialog = TaskDialog()

    picker_with_time = DateTimePickerPopup(dialog, include_time=True)
    assert picker_with_time.include_time
    assert not picker_with_time.time_panel.isHidden()
    picker_with_time.hour_spin.setValue(18)
    picker_with_time.minute_spin.setValue(45)
    picker_with_time.apply_selection()
    assert dialog.due_edit.time().hour() == 18
    assert dialog.due_edit.time().minute() == 45
    picker_with_time.close()

    picker_without_time = DateTimePickerPopup(dialog, include_time=False)
    assert picker_without_time.time_panel.isHidden()
    picker_without_time.close()

    dialog.close()


def test_tag_widgets_truncate_long_names_and_group_candidates(qapp):
    long_tag = {"name": "ImportantLong", "color": "#2563EB"}
    short_tag = {"name": "Home", "color": "#059669"}
    dialog = TaskDialog(all_tags=[long_tag, short_tag])

    long_button = next(
        button for button in dialog.findChildren(QPushButton) if button.toolTip() == "ImportantLong"
    )
    assert long_button.text() == "Impo"
    candidate_frame = dialog.findChild(QFrame, "tagCandidateFrame")
    assert candidate_frame is not None

    pill = TagPill(long_tag)
    assert pill.text() == "Impo"
    assert pill.toolTip() == "ImportantLong"

    short_pill = TagPill(short_tag)
    assert short_pill.text() == "Home"
    assert short_pill.toolTip() == ""

    card = TaskCardWidget(
        task=type(
            "TaskStub",
            (),
            {
                "id": "1",
                "title": "Tagged",
                "completed": False,
                "due_date": None,
                "reminder_minutes": None,
                "tags": [long_tag, short_tag],
            },
        )()
    )
    assert card.findChild(DragScrollArea) is not None

    card.close()
    dialog.close()


def test_edit_dialog_shows_selected_and_candidate_tags(qapp):
    selected = {"name": "Work", "color": "#2563EB"}
    candidate = {"name": "Home", "color": "#059669"}
    task = type(
        "TaskStub",
        (),
        {
            "id": "1",
            "title": "Tagged",
            "description": "",
            "due_date": None,
            "has_time": False,
            "reminder_minutes": None,
            "tags": [selected],
        },
    )()
    dialog = TaskDialog(task=task, all_tags=[selected, candidate])

    assert any(
        button.text() == "Work" and button.isVisibleTo(dialog)
        for button in dialog.findChildren(QPushButton)
    )
    assert not any(
        button.text() == "Home" and button.isVisibleTo(dialog)
        for button in dialog.findChildren(QPushButton)
    )

    dialog.toggle_tag_picker()

    assert any(
        button.text() == "Home" and button.isVisibleTo(dialog)
        for button in dialog.findChildren(QPushButton)
    )
    assert dialog.tag_container.sizeHint().height() > 0

    dialog.close()
