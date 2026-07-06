from datetime import datetime

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    COLORS,
    QUADRANT_CONFIGS,
    STYLE_CARD_CONTAINER,
    STYLE_CARD_META,
    STYLE_CARD_TITLE,
    STYLE_CHECKBOX,
    STYLE_COMPLETED_TEXT,
    STYLE_CUSTOM_POPUP,
)
from app.models.task import Task
from app.resources.strings import Strings
from app.ui.components.markdown_text_edit import MarkdownTextEdit


class TagPill(QLabel):
    double_clicked = pyqtSignal(str)

    def __init__(self, tag: dict[str, str]):
        display_name = self._display_name(tag["name"])
        super().__init__(display_name)
        self.tag = tag
        self.drag_scroll_area = None
        self.drag_start = None
        self.scroll_start = 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if display_name != tag["name"]:
            self.setToolTip(tag["name"])
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {tag.get("color", "#6B7280")};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 700;
            }}
            """
        )
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit(self.tag["name"])
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_scroll_area = self._find_drag_scroll_area()
            if self.drag_scroll_area is not None:
                self.drag_start = event.globalPosition().toPoint()
                self.scroll_start = self.drag_scroll_area.horizontalScrollBar().value()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_scroll_area is not None and self.drag_start is not None:
            delta = event.globalPosition().toPoint().x() - self.drag_start.x()
            self.drag_scroll_area.horizontalScrollBar().setValue(self.scroll_start - delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.drag_scroll_area = None
        self.drag_start = None
        super().mouseReleaseEvent(event)

    def _display_name(self, name: str) -> str:
        return name if len(name) <= 4 else name[:4]

    def _find_drag_scroll_area(self):
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, DragScrollArea):
                return parent
            parent = parent.parent()
        return None


class DragScrollArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.drag_start = None
        self.scroll_start = 0
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.position().toPoint()
            self.scroll_start = self.horizontalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.drag_start is not None:
            delta = event.position().toPoint().x() - self.drag_start.x()
            self.horizontalScrollBar().setValue(self.scroll_start - delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.drag_start is not None:
            self.drag_start = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TaskInfoPopup(QWidget):
    def __init__(self, task: Task):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setup_ui(task)

    def setup_ui(self, task: Task) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        container = QFrame()
        container.setObjectName("popupContainer")
        container.setStyleSheet(STYLE_CUSTOM_POPUP)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(15, 12, 15, 12)
        v_layout.setSpacing(4)

        # Title is already visible on the card — only show description
        # in the popup, up to 10 lines of content (≈200 px at 13px font).
        if task.description and task.description.strip():
            # Use a read-only MarkdownTextEdit to render Markdown descriptions.
            # Reusing MarkdownTextEdit gives us loadResource override for
            # proper image resolution and baseUrl handling.
            popup_content_width = 250  # 300 - 10*2 (outer) - 15*2 (container)
            desc_view = MarkdownTextEdit()
            desc_view.setReadOnly(True)
            desc_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            desc_view.setFrameShape(QFrame.Shape.NoFrame)
            desc_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            desc_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            desc_view.setStyleSheet(
                "font-size: 13px; color: #4B5563; background: transparent; padding: 0px; margin: 0px;"
            )

            # Force the document to lay out at the popup's content width
            # so that document().size().height() returns a correct value.
            # (Before the widget is shown, the viewport width is 0, so
            # QTextDocument cannot calculate line wrapping and returns
            # height ≈ 0.  When the popup is later shown, QTextEdit's
            # resizeEvent will override this with the actual viewport width.)
            desc_view.document().setTextWidth(popup_content_width)
            desc_view.set_description(task.description)

            # Scale images to 90 % of the popup content width.
            desc_view._scale_images_to_width(int(popup_content_width * 0.9))

            # Limit to approximately 10 lines of content (≈200 px).
            doc_height = desc_view.document().size().height()
            max_height = 200

            if doc_height <= max_height:
                desc_view.setFixedHeight(int(doc_height) + 4)
                v_layout.addWidget(desc_view)
            else:
                desc_view.setFixedHeight(max_height)
                v_layout.addWidget(desc_view)

                # Add a visible truncation indicator below the clipped view.
                ellipsis = QLabel("…")
                ellipsis.setStyleSheet(
                    "font-size: 12px; color: #9CA3AF; border: none; background: transparent;"
                )
                v_layout.addWidget(ellipsis)

        main_layout.addWidget(container)
        self.setFixedWidth(300)


class TaskCardWidget(QWidget):
    def __init__(
        self, task: Task, on_status_change=None, on_tag_double_clicked=None, archived=False
    ):
        super().__init__()
        self.task = task
        self.popup = None
        self.on_status_change = on_status_change
        self.on_tag_double_clicked = on_tag_double_clicked
        self.archived = archived
        self.has_tags = bool(task.tags)
        self.has_bottom_info = bool(task.due_date or task.reminder_minutes is not None)
        self.shadow_margin = 4
        self.card_padding = 24
        self.checkbox_column = 30
        self.bottom_info_height = 24
        self.spacing = 4

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE_CARD_CONTAINER)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.shadow_margin, self.shadow_margin, self.shadow_margin, self.shadow_margin
        )
        layout.setSpacing(0)

        self.surface = QFrame()
        self.surface.setObjectName("taskCardSurface")
        self.surface.setStyleSheet(STYLE_CARD_CONTAINER)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(17, 24, 39, 24))
        shadow.setOffset(0, 3)
        self.surface.setGraphicsEffect(shadow)
        layout.addWidget(self.surface)

        content_layout = QVBoxLayout(self.surface)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(self.spacing)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(task.completed)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setStyleSheet(STYLE_CHECKBOX)
        self.checkbox.stateChanged.connect(self.handle_checkbox_change)
        top_layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignTop)

        self.lbl_title = QLabel(task.title)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top_layout.addWidget(self.lbl_title, 1)

        content_layout.addLayout(top_layout)
        self.update_visual_style(task.completed)

        if self.has_tags:
            tag_container = QWidget()
            tag_layout = QHBoxLayout(tag_container)
            tag_layout.setSpacing(5)
            tag_layout.setContentsMargins(0, 0, 0, 0)
            for tag in task.tags:
                pill = TagPill(tag)
                pill.double_clicked.connect(self.handle_tag_double_click)
                tag_layout.addWidget(pill)
            tag_container.adjustSize()

            tag_row_layout = QHBoxLayout()
            tag_row_layout.setSpacing(0)
            tag_row_layout.setContentsMargins(self.checkbox_column, 2, 0, 2)
            self.tag_scroll = DragScrollArea()
            self.tag_scroll.setFixedHeight(22)
            self.tag_scroll.setWidget(tag_container)
            tag_row_layout.addWidget(self.tag_scroll)
            content_layout.addLayout(tag_row_layout)
        else:
            self.tag_scroll = None

        if self.has_bottom_info:
            info_layout = QHBoxLayout()
            info_layout.setSpacing(8)
            info_layout.setContentsMargins(self.checkbox_column, 0, 0, 0)

            if task.due_date:
                lbl_date = QLabel(self._format_due_date())
                lbl_date.setStyleSheet(self._date_style())
                info_layout.addWidget(lbl_date)

            if task.reminder_minutes is not None:
                lbl_reminder = QLabel(Strings.get("card_reminder"))
                lbl_reminder.setStyleSheet(STYLE_CARD_META)
                info_layout.addWidget(lbl_reminder)

            info_layout.addStretch()
            content_layout.addLayout(info_layout)

        content_layout.addStretch()

    def _format_due_date(self) -> str:
        try:
            due_at = datetime.fromisoformat(self.task.due_date or "")
        except ValueError:
            return Strings.get("card_due_prefix")

        value = (
            due_at.strftime("%m-%d %H:%M") if self.task.has_time else due_at.strftime("%Y-%m-%d")
        )
        return f"{Strings.get('card_due_prefix')} {value}"

    def _date_style(self) -> str:
        try:
            due_at = datetime.fromisoformat(self.task.due_date or "")
        except ValueError:
            return STYLE_CARD_META

        if due_at < datetime.now() and not self.task.completed:
            return f"""
                QLabel {{
                    font-size: 11px;
                    color: {COLORS["danger"]};
                    font-weight: 700;
                    border: none;
                    background: transparent;
                }}
            """
        if not self.task.has_time:
            return f"QLabel {{ font-size: 11px; color: {COLORS['primary']}; font-weight: 600; border: none; background: transparent; }}"
        return STYLE_CARD_META

    def handle_checkbox_change(self, state: int) -> None:
        is_checked = state == Qt.CheckState.Checked.value
        self.update_visual_style(is_checked)
        if self.on_status_change:
            self.on_status_change(self.task.id, is_checked)

    def update_visual_style(self, completed: bool) -> None:
        self.lbl_title.setStyleSheet(STYLE_COMPLETED_TEXT if completed else STYLE_CARD_TITLE)
        # Only apply quadrant background color for archived cards (归档箱).
        # Cards that are still in the quadrant should keep the default white
        # style even when completed — they will be moved to archive soon.
        if completed and self.archived:
            quadrant_bg = self._quadrant_bg_color()
            if quadrant_bg:
                self.setStyleSheet("TaskCardWidget { background: transparent; }")
                self.surface.setStyleSheet(
                    f"QFrame#taskCardSurface {{ "
                    f"background-color: {quadrant_bg}; "
                    f"border-radius: 12px; "
                    f"border: 1px solid {COLORS['border']}; }}"
                    f"QFrame#taskCardSurface:hover {{ "
                    f"border: 1px solid {COLORS['border_hover']}; }}"
                )
            else:
                self.setStyleSheet(STYLE_CARD_CONTAINER)
                self.surface.setStyleSheet(STYLE_CARD_CONTAINER)
        else:
            self.setStyleSheet(STYLE_CARD_CONTAINER)
            self.surface.setStyleSheet(STYLE_CARD_CONTAINER)

    def _quadrant_bg_color(self) -> str | None:
        """Return the quadrant's light background color for the current task."""
        qid = self.task.quadrant
        for conf in QUADRANT_CONFIGS:
            if conf["id"] == qid:
                return conf["bg"]
        return None

    def update_preferred_height(self, target_width: int) -> int:
        target_width = max(120, target_width)
        self.setFixedWidth(target_width)
        text_width = max(80, target_width - self.card_padding - self.checkbox_column - 8)
        self.lbl_title.setFixedWidth(text_width)
        if self.tag_scroll is not None:
            self.tag_scroll.setFixedWidth(text_width)
            widget = self.tag_scroll.widget()
            if widget is not None:
                widget.adjustSize()

        metrics = self.lbl_title.fontMetrics()
        rect = metrics.boundingRect(
            0,
            0,
            text_width,
            10_000,
            Qt.TextFlag.TextWordWrap,
            self.task.title,
        )
        total_height = (self.shadow_margin * 2) + self.card_padding + rect.height()
        if self.has_bottom_info:
            total_height += self.bottom_info_height + self.spacing
        if self.has_tags:
            total_height += 24 + self.spacing
        return max(54, total_height)

    def handle_tag_double_click(self, tag_name: str) -> None:
        if self.on_tag_double_clicked:
            self.on_tag_double_clicked(tag_name)

    def enterEvent(self, event):
        if not self.popup and (self.task.description or "").strip():
            self.popup = TaskInfoPopup(self.task)
            self.popup.move(QCursor.pos() + QPoint(15, 15))
            self.popup.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.popup:
            self.popup.close()
            self.popup = None
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        if self.popup:
            self.popup.move(QCursor.pos() + QPoint(15, 15))
        super().mouseMoveEvent(event)
