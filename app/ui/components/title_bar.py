from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from app.config import (
    APP_LOGO_PATH,
    ICON_CLOSE_PATH,
    ICON_CLOSE_WHITE_PATH,
    ICON_MAXIMIZE_PATH,
    ICON_MINIMIZE_PATH,
    ICON_RESTORE_PATH,
    STYLE_TITLE_BAR,
    STYLE_TITLE_BAR_BUTTONS,
    TITLE_BAR_HEIGHT,
)
from app.resources.strings import Strings


class TitleBar(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.window_ref = parent
        self._drag_pos = None
        self.setup_ui()

    def setup_ui(self) -> None:
        self.setObjectName("titleBar")
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setStyleSheet(STYLE_TITLE_BAR + STYLE_TITLE_BAR_BUTTONS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Left: icon + title --
        icon_label = QLabel()
        icon_label.setObjectName("titleBarIcon")
        pixmap = QPixmap(APP_LOGO_PATH)
        scaled = pixmap.scaled(
            16,
            16,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        icon_label.setPixmap(scaled)
        icon_label.setFixedSize(16, 16)
        layout.addWidget(icon_label)

        title_label = QLabel(Strings.get("window_main_title"))
        title_label.setObjectName("titleBarTitle")
        layout.addWidget(title_label)

        layout.addStretch()

        # -- Right: window control buttons --
        self.btn_minimize = self._create_button(
            ICON_MINIMIZE_PATH,
            "最小化",
            self._handle_minimize,
            "titleBarBtn",
        )
        layout.addWidget(self.btn_minimize)

        self.btn_maximize = self._create_button(
            ICON_MAXIMIZE_PATH,
            "最大化",
            self._handle_maximize_restore,
            "titleBarBtn",
        )
        layout.addWidget(self.btn_maximize)

        # Close button uses dual-mode icon: gray normal, white on hover (red bg)
        close_icon = QIcon()
        close_icon.addFile(ICON_CLOSE_PATH, QSize(16, 16), QIcon.Mode.Normal, QIcon.State.Off)
        close_icon.addFile(ICON_CLOSE_WHITE_PATH, QSize(16, 16), QIcon.Mode.Active, QIcon.State.Off)
        self.btn_close = self._create_button_with_icon(
            close_icon,
            "关闭",
            self._handle_close,
            "titleBarClose",
        )
        layout.addWidget(self.btn_close)

    def _create_button(
        self,
        icon_path: str,
        tooltip: str,
        callback,
        object_name: str,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(46, TITLE_BAR_HEIGHT)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    def _create_button_with_icon(
        self,
        icon: QIcon,
        tooltip: str,
        callback,
        object_name: str,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setIcon(icon)
        btn.setIconSize(QSize(16, 16))
        btn.setFixedSize(46, TITLE_BAR_HEIGHT)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    # -- Window control handlers --

    def _handle_minimize(self) -> None:
        self.window_ref.showMinimized()

    def _handle_maximize_restore(self) -> None:
        if self.window_ref.isMaximized():
            self.window_ref.showNormal()
            self.btn_maximize.setIcon(QIcon(ICON_MAXIMIZE_PATH))
        else:
            self.window_ref.showMaximized()
            self.btn_maximize.setIcon(QIcon(ICON_RESTORE_PATH))

    def _handle_close(self) -> None:
        self.window_ref.close()

    # -- Mouse events for drag-move & double-click toggle --

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.window_ref.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.window_ref.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_maximize_restore()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
