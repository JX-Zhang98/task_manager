from typing import Dict

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QLabel, QGridLayout, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from app.config import QUADRANT_CONFIGS, STYLE_MENU, style_quadrant_container, style_quadrant_header
from app.resources.strings import Strings
from app.services.task_service import TaskService
from app.ui.components.draggable_list import DraggableListWidget
from app.ui.components.task_card import TaskCardWidget
from app.ui.components.task_dialog import TaskDialog


class MatrixView(QWidget):
    HEADER_TAG_MAX_LENGTH = 8

    def __init__(self, service: TaskService, parent=None):
        super().__init__(parent)
        self.service = service
        self.lists: Dict[str, DraggableListWidget] = {}
        self.active_tag_filter = None
        self.headers: Dict[str, QLabel] = {}
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QGridLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        for conf in QUADRANT_CONFIGS:
            container = QWidget()
            container.setStyleSheet(style_quadrant_container(conf["bg"]))
            v_layout = QVBoxLayout(container)
            v_layout.setContentsMargins(12, 12, 12, 12)
            v_layout.setSpacing(10)

            header = QLabel(conf["title"])
            header.setStyleSheet(style_quadrant_header(conf["text"]))
            self.headers[conf["id"]] = header
            v_layout.addWidget(header)

            list_widget = DraggableListWidget(conf["id"], self.service)
            list_widget.itemDoubleClicked.connect(self.handle_double_click)
            list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(
                lambda pos, lw=list_widget: self.show_context_menu(pos, lw)
            )

            self.lists[conf["id"]] = list_widget
            v_layout.addWidget(list_widget)
            layout.addWidget(container, conf["row"], conf["col"])

    def refresh(self) -> None:
        for list_widget in self.lists.values():
            list_widget.clear()

        for task in self.filtered_matrix_tasks():
            list_widget = self.lists.get(task.quadrant)
            if list_widget is None:
                continue

            item = QListWidgetItem(list_widget)
            item.setData(Qt.ItemDataRole.UserRole, task.id)

            widget = TaskCardWidget(
                task,
                on_status_change=self.service.toggle_complete,
                on_tag_double_clicked=self.filter_by_tag,
            )
            current_width = self.card_width(list_widget, fallback=200)
            height = widget.update_preferred_height(current_width)
            item.setSizeHint(QSize(current_width, height))
            list_widget.setItemWidget(item, widget)
        self.update_headers()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_layout()

    def card_width(self, list_widget: DraggableListWidget, fallback: int) -> int:
        current_width = list_widget.viewport().width() - 20
        return current_width if current_width > 0 else fallback

    def adjust_layout(self) -> None:
        for list_widget in self.lists.values():
            current_width = self.card_width(list_widget, fallback=200)
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                widget = list_widget.itemWidget(item)
                if widget is not None:
                    height = widget.update_preferred_height(current_width)
                    item.setSizeHint(QSize(current_width, height))

    def handle_double_click(self, item) -> None:
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = self.service.get_task(task_id)
        if task:
            self.open_task_dialog(task)

    def show_context_menu(self, pos: QPoint, list_widget: DraggableListWidget) -> None:
        item = list_widget.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(STYLE_MENU)
        delete_action = QAction(Strings.get("menu_delete"), self)
        delete_action.triggered.connect(
            lambda: self.service.delete_task(item.data(Qt.ItemDataRole.UserRole))
        )
        menu.addAction(delete_action)
        menu.exec(list_widget.mapToGlobal(pos))

    def open_task_dialog(self, task) -> None:
        dialog = TaskDialog(self, task, self.service.get_all_tags())
        if dialog.exec():
            data = dialog.result_data
            self.service.update_task(
                task.id,
                data["title"],
                data["description"],
                data["due_date"],
                data["has_time"],
                data["reminder_minutes"],
                data["tags"],
            )

    def filtered_matrix_tasks(self):
        tasks = self.service.get_visible_matrix_tasks()
        if not self.active_tag_filter:
            return tasks
        key = self.active_tag_filter.casefold()
        return [task for task in tasks if any(tag["name"].casefold() == key for tag in task.tags)]

    def filter_by_tag(self, tag_name: str) -> None:
        if self.active_tag_filter == tag_name:
            self.active_tag_filter = None
        else:
            self.active_tag_filter = tag_name
        self.refresh()

    def update_headers(self) -> None:
        for conf in QUADRANT_CONFIGS:
            title = conf["title"]
            if self.active_tag_filter:
                title = f"{title} #{self._header_tag_text(self.active_tag_filter)}"
                self.headers[conf["id"]].setToolTip(self.active_tag_filter)
            else:
                self.headers[conf["id"]].setToolTip("")
            self.headers[conf["id"]].setText(title)

    def _header_tag_text(self, tag_name: str) -> str:
        if len(tag_name) <= self.HEADER_TAG_MAX_LENGTH:
            return tag_name
        return f"{tag_name[: self.HEADER_TAG_MAX_LENGTH]}..."
