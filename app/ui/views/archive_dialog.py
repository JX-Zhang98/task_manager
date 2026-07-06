from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from app.config import (
    APP_LOGO_PATH,
    STYLE_ARCHIVE_LIST,
    STYLE_ARCHIVE_TITLE,
    STYLE_BTN_SECONDARY,
    STYLE_EMPTY_STATE,
)
from app.services.task_service import TaskService
from app.ui.components.task_card import TaskCardWidget
from app.resources.strings import Strings


class ArchiveDialog(QDialog):
    def __init__(self, service: TaskService, parent=None):
        super().__init__(parent)
        self.service = service
        self.empty_label = None
        self.setWindowTitle(Strings.get("archive_window_title"))
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.resize(450, 600)
        self.setup_ui()
        self.load_data()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(Strings.get("archive_title"))
        title.setStyleSheet(STYLE_ARCHIVE_TITLE)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(STYLE_ARCHIVE_LIST)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.list_widget)

        self.empty_label = QLabel(Strings.get("archive_empty"))
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(STYLE_EMPTY_STATE)
        layout.addWidget(self.empty_label)

        btn_close = QPushButton(Strings.get("btn_close"))
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_data(self) -> None:
        self.list_widget.clear()
        archived_tasks = self.service.get_archived_tasks()
        self.empty_label.setVisible(not archived_tasks)

        current_width = self.list_widget.viewport().width()
        if current_width <= 0:
            current_width = 300

        for task in archived_tasks:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, task.id)

            widget = TaskCardWidget(task, on_status_change=self.handle_restore, archived=True)
            height = widget.update_preferred_height(current_width)
            item.setSizeHint(QSize(current_width, height))
            self.list_widget.setItemWidget(item, widget)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.adjust_layout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_layout()

    def adjust_layout(self) -> None:
        current_width = self.list_widget.viewport().width() - 10
        if current_width <= 0:
            return

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            widget = self.list_widget.itemWidget(item)
            if widget is not None:
                height = widget.update_preferred_height(current_width)
                item.setSizeHint(QSize(current_width, height))

    def handle_restore(self, task_id: str, is_checked: bool) -> None:
        self.service.toggle_complete(task_id, is_checked)
        if not is_checked:
            self.load_data()
            QTimer.singleShot(0, self.adjust_layout)
