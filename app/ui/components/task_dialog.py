from datetime import datetime

from PyQt6.QtCore import QDate, QDateTime, QPoint, QRect, QSize, QTime, Qt
from PyQt6.QtGui import QColor, QIcon, QTextCharFormat
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDial,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    APP_LOGO_PATH,
    STYLE_BTN_PRIMARY,
    STYLE_BTN_SECONDARY,
    STYLE_CHECKBOX,
    STYLE_CALENDAR,
    STYLE_COMBOBOX,
    STYLE_DIALOG_CONTAINER,
    STYLE_FORM_LABEL,
    STYLE_INPUT,
    STYLE_TIME_PICKER,
    TAG_COLORS,
)
from app.models.task import Task
from app.resources.strings import Strings


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        self.item_list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item) -> None:
        self.item_list.append(item)

    def count(self) -> int:
        return len(self.item_list)

    def itemAt(self, index: int):
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        margins = self.contentsMargins()
        width = sum(item.sizeHint().width() for item in self.item_list)
        if self.item_list:
            width += self.spacing() * (len(self.item_list) - 1)
        height = max((item.sizeHint().height() for item in self.item_list), default=0)
        return QSize(
            width + margins.left() + margins.right(),
            height + margins.top() + margins.bottom(),
        )

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self.item_list:
            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()


class ClickableDateTimeEdit(QDateTimeEdit):
    def __init__(self, parent_dialog: "TaskDialog"):
        super().__init__(parent_dialog)
        self.parent_dialog = parent_dialog
        self.setReadOnly(True)
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched == self.lineEdit() and self.isEnabled():
            if event.type() == event.Type.MouseButtonPress:
                self.parent_dialog.open_date_time_picker()
                return True
            if event.type() == event.Type.KeyPress and event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
                Qt.Key.Key_Space,
            ):
                self.parent_dialog.open_date_time_picker()
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        if self.isEnabled():
            self.parent_dialog.open_date_time_picker()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if self.isEnabled() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.parent_dialog.open_date_time_picker()
            event.accept()
            return
        super().keyPressEvent(event)


class DateTimePickerPopup(QWidget):
    def __init__(self, owner: "TaskDialog", include_time: bool):
        super().__init__(owner, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.owner = owner
        self.include_time = include_time
        self.setObjectName("dateTimePickerPopup")
        self.setStyleSheet(STYLE_TIME_PICKER)
        self.setup_ui()
        self.load_from_edit()

    def setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self.calendar = QCalendarWidget()
        self.owner.configure_calendar_widget(self.calendar)
        self.calendar.setSelectedDate(self.owner.due_edit.date())
        self.calendar.clicked.connect(self.apply_selection)
        layout.addWidget(self.calendar)

        self.time_panel = QFrame()
        self.time_panel.setObjectName("timePanel")
        time_layout = QVBoxLayout(self.time_panel)
        time_layout.setContentsMargins(16, 14, 16, 14)
        time_layout.setSpacing(10)

        title = QLabel("24 小时时间")
        title.setObjectName("timeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_layout.addWidget(title)

        self.time_value = QLabel()
        self.time_value.setObjectName("timeValue")
        self.time_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_layout.addWidget(self.time_value)

        dial_layout = QGridLayout()
        dial_layout.setHorizontalSpacing(10)
        dial_layout.setVerticalSpacing(4)

        self.hour_dial = self.create_dial(0, 23)
        self.minute_dial = self.create_dial(0, 59)
        self.hour_dial.valueChanged.connect(self.sync_hour_from_dial)
        self.minute_dial.valueChanged.connect(self.sync_minute_from_dial)
        dial_layout.addWidget(self.hour_dial, 0, 0)
        dial_layout.addWidget(self.minute_dial, 0, 1)

        hour_label = QLabel("时")
        minute_label = QLabel("分")
        for label in (hour_label, minute_label):
            label.setObjectName("timeCaption")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dial_layout.addWidget(hour_label, 1, 0)
        dial_layout.addWidget(minute_label, 1, 1)
        time_layout.addLayout(dial_layout)

        spin_layout = QHBoxLayout()
        self.hour_spin = self.create_spin(0, 23)
        self.minute_spin = self.create_spin(0, 59)
        self.hour_spin.valueChanged.connect(self.sync_hour_from_spin)
        self.minute_spin.valueChanged.connect(self.sync_minute_from_spin)
        spin_layout.addWidget(self.hour_spin)
        spin_layout.addWidget(self.minute_spin)
        time_layout.addLayout(spin_layout)

        btn_done = QPushButton("确定")
        btn_done.setObjectName("pickerDoneButton")
        btn_done.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_done.clicked.connect(self.close)
        time_layout.addWidget(btn_done)

        layout.addWidget(self.time_panel)
        self.time_panel.setVisible(self.include_time)

    def create_dial(self, minimum: int, maximum: int) -> QDial:
        dial = QDial()
        dial.setRange(minimum, maximum)
        dial.setNotchesVisible(True)
        dial.setWrapping(True)
        dial.setFixedSize(108, 108)
        return dial

    def create_spin(self, minimum: int, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setWrapping(True)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        return spin

    def load_from_edit(self) -> None:
        current = self.owner.due_edit.dateTime()
        self.calendar.setSelectedDate(current.date())
        hour = current.time().hour()
        minute = current.time().minute()
        self.hour_dial.setValue(hour)
        self.minute_dial.setValue(minute)
        self.hour_spin.setValue(hour)
        self.minute_spin.setValue(minute)
        self.update_time_value()

    def sync_hour_from_dial(self, value: int) -> None:
        self.hour_spin.blockSignals(True)
        self.hour_spin.setValue(value)
        self.hour_spin.blockSignals(False)
        self.apply_selection()

    def sync_minute_from_dial(self, value: int) -> None:
        self.minute_spin.blockSignals(True)
        self.minute_spin.setValue(value)
        self.minute_spin.blockSignals(False)
        self.apply_selection()

    def sync_hour_from_spin(self, value: int) -> None:
        self.hour_dial.blockSignals(True)
        self.hour_dial.setValue(value)
        self.hour_dial.blockSignals(False)
        self.apply_selection()

    def sync_minute_from_spin(self, value: int) -> None:
        self.minute_dial.blockSignals(True)
        self.minute_dial.setValue(value)
        self.minute_dial.blockSignals(False)
        self.apply_selection()

    def apply_selection(self) -> None:
        time = self.owner.due_edit.time()
        if self.include_time:
            time = QTime(self.hour_spin.value(), self.minute_spin.value())
        self.owner.due_edit.setDateTime(QDateTime(self.calendar.selectedDate(), time))
        self.update_time_value()

    def update_time_value(self) -> None:
        self.time_value.setText(f"{self.hour_spin.value():02d}:{self.minute_spin.value():02d}")


class TaskDialog(QDialog):
    def __init__(self, parent=None, task: Task = None, all_tags: list[dict[str, str]] | None = None):
        super().__init__(parent)
        self.task = task
        self.all_tags = self._normalize_tags(all_tags or [])
        self.selected_tags = self._normalize_tags(task.tags if task else [])
        self.show_tag_picker = task is None
        self.result_data = None
        self.reminders = [
            (Strings.get("remind_none"), None),
            (Strings.get("remind_on_time"), 0),
            (Strings.get("remind_5min"), 5),
            (Strings.get("remind_15min"), 15),
            (Strings.get("remind_30min"), 30),
            (Strings.get("remind_1h"), 60),
            (Strings.get("remind_1d"), 1440),
        ]

        title_key = "dialog_edit_title" if task else "dialog_add_title"
        self.setWindowTitle(Strings.get(title_key))
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.setStyleSheet(STYLE_DIALOG_CONTAINER)
        self.resize(520, 640)
        self.setup_ui()
        self.load_task()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(14)

        lbl_title = QLabel(Strings.get("label_title"))
        lbl_title.setStyleSheet(STYLE_FORM_LABEL)
        layout.addWidget(lbl_title)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(Strings.get("placeholder_title"))
        self.title_edit.setStyleSheet(STYLE_INPUT)
        layout.addWidget(self.title_edit)

        lbl_desc = QLabel(Strings.get("label_desc"))
        lbl_desc.setStyleSheet(STYLE_FORM_LABEL)
        layout.addWidget(lbl_desc)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText(Strings.get("placeholder_desc"))
        self.desc_edit.setStyleSheet(STYLE_INPUT)
        self.desc_edit.setFixedHeight(120)
        layout.addWidget(self.desc_edit)

        self.date_time_popup = None
        self.due_edit = ClickableDateTimeEdit(self)
        self.due_edit.setCalendarPopup(True)
        self.due_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.due_edit.setDateTime(QDateTime.currentDateTime())
        self.due_edit.setStyleSheet(STYLE_INPUT)
        layout.addWidget(self.due_edit)

        date_option_layout = QHBoxLayout()
        date_option_layout.setContentsMargins(0, 0, 0, 0)

        self.has_date_check = QCheckBox(Strings.get("label_has_date"))
        self.has_date_check.setStyleSheet(STYLE_CHECKBOX)
        self.has_date_check.setChecked(True)
        self.has_date_check.stateChanged.connect(self.update_date_controls)
        date_option_layout.addWidget(self.has_date_check)

        date_option_layout.addStretch()

        self.has_time_check = QCheckBox(Strings.get("label_has_time"))
        self.has_time_check.setStyleSheet(STYLE_CHECKBOX)
        self.has_time_check.setChecked(False)
        self.has_time_check.stateChanged.connect(self.update_date_controls)
        date_option_layout.addWidget(self.has_time_check)

        layout.addLayout(date_option_layout)

        lbl_reminder = QLabel(Strings.get("label_reminder"))
        lbl_reminder.setStyleSheet(STYLE_FORM_LABEL)
        layout.addWidget(lbl_reminder)

        self.reminder_combo = QComboBox()
        self.reminder_combo.setStyleSheet(STYLE_COMBOBOX)
        for text, value in self.reminders:
            self.reminder_combo.addItem(text, value)
        layout.addWidget(self.reminder_combo)

        lbl_tags = QLabel("标签")
        lbl_tags.setStyleSheet(STYLE_FORM_LABEL)
        layout.addWidget(lbl_tags)

        self.tag_container = QWidget()
        self.tag_layout = QVBoxLayout(self.tag_container)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(8)
        layout.addWidget(self.tag_container)
        self.refresh_tag_controls()

        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        btn_cancel = QPushButton(Strings.get("btn_cancel"))
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(STYLE_BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton(Strings.get("btn_save"))
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(STYLE_BTN_PRIMARY)
        btn_save.clicked.connect(self.save_task)

        button_layout.addWidget(btn_cancel)
        button_layout.addWidget(btn_save)
        layout.addLayout(button_layout)

        self.update_date_controls()

    def configure_calendar_widget(self, calendar: QCalendarWidget) -> None:
        calendar.setGridVisible(False)
        calendar.setMinimumSize(360, 320)
        calendar.setVerticalHeaderFormat(calendar.VerticalHeaderFormat.NoVerticalHeader)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        calendar.setStyleSheet(STYLE_CALENDAR)

        day_format = QTextCharFormat()
        day_format.setForeground(QColor("#111827"))
        for day in Qt.DayOfWeek:
            calendar.setWeekdayTextFormat(day, day_format)

        for object_name, text in (
            ("qt_calendar_prevmonth", "<"),
            ("qt_calendar_nextmonth", ">"),
        ):
            button = calendar.findChild(QToolButton, object_name)
            if button:
                button.setIcon(QIcon())
                button.setText(text)
                button.setCursor(Qt.CursorShape.PointingHandCursor)

    def open_date_time_picker(self) -> None:
        if not self.has_date_check.isChecked():
            return

        if self.date_time_popup is not None:
            self.date_time_popup.close()

        self.date_time_popup = DateTimePickerPopup(self, self.has_time_check.isChecked())
        pos = self.due_edit.mapToGlobal(QPoint(0, self.due_edit.height() + 6))
        self.date_time_popup.move(pos)
        self.date_time_popup.show()

    def load_task(self) -> None:
        if not self.task:
            return

        self.title_edit.setText(self.task.title)
        self.desc_edit.setPlainText(self.task.description)

        has_due_date = bool(self.task.due_date)
        self.has_date_check.setChecked(has_due_date)
        self.has_time_check.setChecked(bool(self.task.has_time))
        if self.task.due_date:
            try:
                due_at = datetime.fromisoformat(self.task.due_date)
                self.due_edit.setDateTime(
                    QDateTime(
                        QDate(due_at.year, due_at.month, due_at.day),
                        QTime(due_at.hour, due_at.minute),
                    )
                )
            except ValueError:
                pass

        for index, (_, value) in enumerate(self.reminders):
            if value == self.task.reminder_minutes:
                self.reminder_combo.setCurrentIndex(index)
                break
        self.update_date_controls()

    def update_date_controls(self) -> None:
        has_date = self.has_date_check.isChecked()
        has_time = self.has_time_check.isChecked()
        self.due_edit.setEnabled(has_date)
        self.has_time_check.setEnabled(has_date)
        self.reminder_combo.setEnabled(has_date)
        self.due_edit.setDisplayFormat("yyyy-MM-dd HH:mm" if has_time else "yyyy-MM-dd")

    def save_task(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            return

        due_date = None
        has_time = False
        if self.has_date_check.isChecked():
            has_time = self.has_time_check.isChecked()
            due_dt = self.due_edit.dateTime().toPyDateTime()
            if not has_time:
                due_dt = due_dt.replace(hour=23, minute=59, second=59, microsecond=0)
            due_date = due_dt.isoformat(timespec="minutes" if has_time else "seconds")

        self.result_data = {
            "title": title,
            "description": self.desc_edit.toPlainText().strip(),
            "due_date": due_date,
            "has_time": has_time,
            "reminder_minutes": self.reminder_combo.currentData() if due_date else None,
            "tags": self.selected_tags,
        }
        self.accept()

    def refresh_tag_controls(self) -> None:
        self._clear_layout(self.tag_layout)

        selected_widget = QWidget()
        selected_layout = FlowLayout(selected_widget, spacing=6)
        for tag in self.selected_tags:
            selected_layout.addWidget(
                self._make_tag_button(tag, lambda checked=False, t=tag: self.remove_tag(t["name"]))
            )

        btn_expand = QPushButton("+")
        btn_expand.setFixedSize(30, 26)
        btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_expand.setStyleSheet(self._tag_add_button_style())
        btn_expand.clicked.connect(self.toggle_tag_picker)
        selected_layout.addWidget(btn_expand)
        self.tag_layout.addWidget(selected_widget)

        if not self.show_tag_picker:
            return

        candidate_frame = QFrame()
        candidate_frame.setObjectName("tagCandidateFrame")
        candidate_frame.setStyleSheet(
            """
            QFrame#tagCandidateFrame {
                background-color: #F6F7F9;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
            }
            """
        )
        candidate_layout = QVBoxLayout(candidate_frame)
        candidate_layout.setContentsMargins(10, 10, 10, 10)
        candidate_layout.setSpacing(8)

        available = [
            tag for tag in self.all_tags if not self._has_selected_tag(tag["name"])
        ]
        if available:
            available_widget = QWidget()
            available_layout = FlowLayout(available_widget, spacing=6)
            for tag in available:
                available_layout.addWidget(
                    self._make_tag_button(
                        tag,
                        lambda checked=False, t=tag: self.add_existing_tag(t),
                    )
                )
            candidate_layout.addWidget(available_widget)

        create_layout = QHBoxLayout()
        create_layout.setContentsMargins(0, 0, 0, 0)
        create_layout.setSpacing(6)
        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setPlaceholderText("新增标签")
        self.new_tag_edit.setStyleSheet(STYLE_INPUT)
        self.new_tag_edit.returnPressed.connect(self.add_new_tag)
        create_layout.addWidget(self.new_tag_edit, 1)

        btn_add_new = QPushButton("+")
        btn_add_new.setFixedSize(34, 32)
        btn_add_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_new.setStyleSheet(self._tag_add_button_style())
        btn_add_new.clicked.connect(self.add_new_tag)
        create_layout.addWidget(btn_add_new)
        candidate_layout.addLayout(create_layout)
        self.tag_layout.addWidget(candidate_frame)

    def toggle_tag_picker(self) -> None:
        self.show_tag_picker = not self.show_tag_picker
        self.refresh_tag_controls()

    def add_existing_tag(self, tag: dict[str, str]) -> None:
        if not self._has_selected_tag(tag["name"]):
            self.selected_tags.append({"name": tag["name"], "color": tag["color"]})
        self.refresh_tag_controls()

    def add_new_tag(self) -> None:
        name = self.new_tag_edit.text().strip()
        if not name:
            return

        existing = self._find_tag(name)
        tag = existing or {"name": name, "color": self._next_tag_color()}
        if not existing:
            self.all_tags.append(tag)
        if not self._has_selected_tag(name):
            self.selected_tags.append({"name": tag["name"], "color": tag["color"]})
        self.show_tag_picker = True
        self.refresh_tag_controls()

    def remove_tag(self, name: str) -> None:
        self.selected_tags = [
            tag for tag in self.selected_tags if tag["name"].casefold() != name.casefold()
        ]
        self.refresh_tag_controls()

    def _find_tag(self, name: str) -> dict[str, str] | None:
        key = name.casefold()
        for tag in [*self.all_tags, *self.selected_tags]:
            if tag["name"].casefold() == key:
                return tag
        return None

    def _has_selected_tag(self, name: str) -> bool:
        return any(tag["name"].casefold() == name.casefold() for tag in self.selected_tags)

    def _next_tag_color(self) -> str:
        names = {tag["name"].casefold() for tag in self.all_tags}
        names.update(tag["name"].casefold() for tag in self.selected_tags)
        return TAG_COLORS[len(names) % len(TAG_COLORS)]

    def _normalize_tags(self, tags: list[dict[str, str]]) -> list[dict[str, str]]:
        from app.domain.task_rules import normalize_tags
        return normalize_tags(tags)

    def _make_tag_button(self, tag: dict[str, str], handler) -> QPushButton:
        display_name = self._tag_display_name(tag["name"])
        button = QPushButton(display_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if display_name != tag["name"]:
            button.setToolTip(tag["name"])
        button.setStyleSheet(self._tag_button_style(tag["color"]))
        button.clicked.connect(handler)
        button.adjustSize()
        button.setFixedSize(button.sizeHint())
        return button

    def _tag_display_name(self, name: str) -> str:
        return name if len(name) <= 4 else name[:4]

    def _tag_button_style(self, color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 4px 9px;
                font-size: 12px;
                font-weight: 700;
            }}
        """

    def _tag_add_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #F3F4F6;
                color: #4B5563;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                font-size: 16px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #E5E7EB;
            }
        """

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.deleteLater()
