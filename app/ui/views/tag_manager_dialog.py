from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    APP_LOGO_PATH,
    COLORS,
    STYLE_ARCHIVE_LIST,
    STYLE_ARCHIVE_TITLE,
    STYLE_BTN_PRIMARY,
    STYLE_BTN_SECONDARY,
    STYLE_MENU,
)
from app.services.task_service import TaskService


class TagEditDialog(QDialog):
    def __init__(self, tag: dict[str, str], parent=None):
        super().__init__(parent)
        self.color = tag.get("color", "#6B7280")
        self.setWindowTitle("编辑标签")
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        self.name_edit = QLineEdit(tag["name"])
        self.name_edit.setPlaceholderText("标签名称")
        layout.addWidget(self.name_edit)

        color_row = QHBoxLayout()
        self.color_preview = QFrame()
        self.color_preview.setFixedSize(28, 28)
        color_row.addWidget(self.color_preview)

        btn_color = QPushButton("选择颜色")
        btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_color.clicked.connect(self.choose_color)
        color_row.addWidget(btn_color)
        color_row.addStretch()
        layout.addLayout(color_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.update_color_preview()

    def choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.color), self, "选择标签颜色")
        if color.isValid():
            self.color = color.name()
            self.update_color_preview()

    def update_color_preview(self) -> None:
        self.color_preview.setStyleSheet(
            f"background-color: {self.color}; border: 1px solid #E5E7EB; border-radius: 6px;"
        )

    def tag_data(self) -> dict[str, str]:
        return {"name": self.name_edit.text().strip(), "color": self.color}


class MergeTagDialog(QDialog):
    def __init__(self, source: dict[str, str], candidates: list[dict[str, str]], parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.setWindowTitle("合并标签")
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        label = QLabel(f"将“{source['name']}”合并至")
        layout.addWidget(label)

        self.combo = QComboBox()
        for tag in candidates:
            self.combo.addItem(tag["name"], tag)
        layout.addWidget(self.combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_tag(self) -> dict[str, str] | None:
        return self.combo.currentData()


class TagRow(QWidget):
    def __init__(self, tag: dict[str, str], count: int):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        swatch = QFrame()
        swatch.setFixedSize(18, 18)
        swatch.setStyleSheet(
            f"background-color: {tag.get('color', '#6B7280')}; border-radius: 5px;"
        )
        layout.addWidget(swatch)

        name = QLabel(tag["name"])
        name.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {COLORS['text_main']};")
        layout.addWidget(name, 1)

        count_label = QLabel(f"{count} 个任务")
        count_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(count_label)


class TagManagerDialog(QDialog):
    def __init__(self, service: TaskService, parent=None):
        super().__init__(parent)
        self.service = service
        self.tags: list[dict[str, str]] = []
        self.setWindowTitle("标签管理")
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.resize(420, 560)
        self.setup_ui()
        self.load_tags()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("标签管理")
        title.setStyleSheet(STYLE_ARCHIVE_TITLE)
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(STYLE_ARCHIVE_LIST)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.list_widget, 1)

        btn_prune = QPushButton("删除所有过期标签")
        btn_prune.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_prune.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_prune.clicked.connect(self.prune_stale_tags)
        layout.addWidget(btn_prune)

        btn_close = QPushButton("关闭")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_tags(self) -> None:
        self.list_widget.clear()
        self.tags = self.service.get_all_tags()
        counts = self.service.get_tag_reference_counts()
        for tag in self.tags:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, tag)
            widget = TagRow(tag, counts.get(tag["name"].casefold(), 0))
            item.setSizeHint(QSize(360, 42))
            self.list_widget.setItemWidget(item, widget)

    def show_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet(STYLE_MENU)
        edit_action = QAction("编辑", self)
        delete_action = QAction("删除", self)
        merge_action = QAction("合并至其他标签", self)
        edit_action.triggered.connect(lambda: self.edit_tag(tag))
        delete_action.triggered.connect(lambda: self.delete_tag(tag))
        merge_action.triggered.connect(lambda: self.merge_tag(tag))
        menu.addAction(edit_action)
        menu.addAction(delete_action)
        menu.addAction(merge_action)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def edit_tag(self, tag: dict[str, str]) -> None:
        dialog = TagEditDialog(tag, self)
        if not dialog.exec():
            return
        data = dialog.tag_data()
        if not data["name"]:
            return
        self.service.rename_tag(tag["name"], data["name"], data["color"])
        self.load_tags()

    def delete_tag(self, tag: dict[str, str]) -> None:
        result = QMessageBox.question(
            self,
            "删除标签",
            f"确定删除“{tag['name']}”吗？所有任务中的此标签都会被移除。",
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.service.delete_tag(tag["name"])
        self.load_tags()

    def merge_tag(self, tag: dict[str, str]) -> None:
        candidates = [
            item
            for item in self.service.get_all_tags()
            if item["name"].casefold() != tag["name"].casefold()
        ]
        if not candidates:
            QMessageBox.information(self, "合并标签", "没有可合并的目标标签。")
            return
        dialog = MergeTagDialog(tag, candidates, self)
        if not dialog.exec():
            return
        target = dialog.selected_tag()
        if target is None:
            return
        self.service.merge_tag(tag["name"], target)
        self.load_tags()

    def prune_stale_tags(self) -> None:
        removed = self.service.prune_stale_tags()
        self.load_tags()
        QMessageBox.information(self, "清理完成", f"已删除 {removed} 个过期标签。")
