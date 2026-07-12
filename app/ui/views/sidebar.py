from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    STYLE_BTN_ARCHIVE,
    STYLE_BTN_SIDEBAR_ADD,
    STYLE_MENU,
    STYLE_SEPARATOR,
    STYLE_SIDEBAR_SUBTITLE,
    STYLE_SIDEBAR_TITLE,
)
from app.resources.strings import Strings
from app.services.task_service import TaskService
from app.ui.components.draggable_list import DraggableListWidget
from app.ui.components.task_card import TaskCardWidget
from app.ui.components.task_dialog import TaskDialog
from app.ui.views.archive_dialog import ArchiveDialog
from app.ui.views.tag_manager_dialog import TagManagerDialog


class SidebarView(QWidget):
    def __init__(self, service: TaskService, parent=None):
        super().__init__(parent)
        self.service = service
        self.setFixedWidth(300)
        self.setObjectName("sidebar")
        self.inbox_list = None
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setSpacing(15)

        title = QLabel(Strings.get("app_title"))
        title.setObjectName("app_title")
        title.setStyleSheet(STYLE_SIDEBAR_TITLE)
        layout.addWidget(title)

        btn_add = QPushButton(Strings.get("btn_add_task"))
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(lambda: self.open_task_dialog(None))
        btn_add.setStyleSheet(STYLE_BTN_SIDEBAR_ADD)
        layout.addWidget(btn_add)

        subtitle = QLabel(Strings.get("subtitle_inbox"))
        subtitle.setStyleSheet(STYLE_SIDEBAR_SUBTITLE)
        layout.addWidget(subtitle)

        self.inbox_list = DraggableListWidget("inbox", self.service)
        self.inbox_list.itemDoubleClicked.connect(self.handle_double_click)
        self.inbox_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.inbox_list.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.inbox_list, 1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(STYLE_SEPARATOR)
        layout.addWidget(line)

        bottom_buttons = QHBoxLayout()
        bottom_buttons.setContentsMargins(0, 0, 0, 0)
        bottom_buttons.setSpacing(8)

        btn_archive = QPushButton(Strings.get("btn_archive"))
        btn_archive.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_archive.setStyleSheet(STYLE_BTN_ARCHIVE)
        btn_archive.clicked.connect(self.open_archive)
        bottom_buttons.addWidget(btn_archive, 1)

        btn_tags = QPushButton("标签管理")
        btn_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_tags.setStyleSheet(STYLE_BTN_ARCHIVE)
        btn_tags.clicked.connect(self.open_tag_manager)
        bottom_buttons.addWidget(btn_tags, 1)

        layout.addLayout(bottom_buttons)

    def refresh(self) -> None:
        self.inbox_list.clear()

        current_width = self.inbox_list.viewport().width() - 20
        if current_width <= 0:
            current_width = 230

        for task in self.service.get_visible_inbox_tasks():
            item = QListWidgetItem(self.inbox_list)
            item.setData(Qt.ItemDataRole.UserRole, task.id)

            widget = TaskCardWidget(task, on_status_change=self.service.toggle_complete)
            height = widget.update_preferred_height(current_width)
            item.setSizeHint(QSize(current_width, height))
            self.inbox_list.setItemWidget(item, widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_layout()

    def card_width(self) -> int:
        current_width = self.inbox_list.viewport().width() - 20
        return current_width if current_width > 0 else 230

    def adjust_layout(self) -> None:
        current_width = self.card_width()
        for index in range(self.inbox_list.count()):
            item = self.inbox_list.item(index)
            widget = self.inbox_list.itemWidget(item)
            if widget is not None:
                height = widget.update_preferred_height(current_width)
                item.setSizeHint(QSize(current_width, height))

    def handle_double_click(self, item) -> None:
        task_id = item.data(Qt.ItemDataRole.UserRole)
        task = self.service.get_task(task_id)
        if task:
            self.open_task_dialog(task)

    def show_context_menu(self, pos: QPoint) -> None:
        item = self.inbox_list.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(STYLE_MENU)
        delete_action = QAction(Strings.get("menu_delete"), self)
        delete_action.triggered.connect(
            lambda: self.service.delete_task(item.data(Qt.ItemDataRole.UserRole))
        )
        menu.addAction(delete_action)
        menu.exec(self.inbox_list.mapToGlobal(pos))

    def open_task_dialog(self, task=None) -> None:
        dialog = TaskDialog(self, task, self.service.get_all_tags())
        if dialog.exec():
            data = dialog.result_data
            if task:
                self.service.update_task(
                    task.id,
                    data["title"],
                    data["description"],
                    data["due_date"],
                    data["has_time"],
                    data["reminder_minutes"],
                    data["tags"],
                )
            else:
                self.service.add_task(
                    data["title"],
                    data["description"],
                    data["due_date"],
                    data["has_time"],
                    data["reminder_minutes"],
                    tags=data["tags"],
                )

    def open_archive(self) -> None:
        dialog = ArchiveDialog(self.service, self)
        dialog.exec()
        self.service.data_changed.emit()

    def open_tag_manager(self) -> None:
        dialog = TagManagerDialog(self.service, self)
        dialog.exec()
        self.service.data_changed.emit()
