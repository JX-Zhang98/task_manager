from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QApplication,
    QSizeGrip,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_LOGO_PATH, RESIZE_MARGIN
from app.resources.strings import Strings
from app.services.task_service import TaskService
from app.ui.components.title_bar import TitleBar
from app.ui.views.matrix import MatrixView
from app.ui.views.sidebar import SidebarView


class SystemResizeHandle(QWidget):
    def __init__(self, window: "MainWindow", edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(window)
        self.window_ref = window
        self.edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self.window_ref.isMaximized()
            and self.window_ref.start_system_resize(self.edges)
        ):
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(Strings.get("window_main_title"))
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.resize(1100, 750)

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)

        self.service = TaskService()
        self.setup_tray()
        self.setup_ui()

        self.service.data_changed.connect(self.refresh_all_views)
        self.service.reminder_triggered.connect(self.show_notification)
        self.refresh_all_views()

    def setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon(APP_LOGO_PATH))

        menu = QMenu()
        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show_window)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)

        menu.addAction(show_action)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        # 双击显示
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def setup_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        frame_layout = QGridLayout(main_widget)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        content_widget = QWidget()
        frame_layout.addWidget(
            self._resize_handle(
                Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                Qt.CursorShape.SizeFDiagCursor,
                RESIZE_MARGIN,
                RESIZE_MARGIN,
            ),
            0,
            0,
        )
        frame_layout.addWidget(
            self._resize_handle(Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor, None, RESIZE_MARGIN),
            0,
            1,
        )
        frame_layout.addWidget(
            self._resize_handle(
                Qt.Edge.TopEdge | Qt.Edge.RightEdge,
                Qt.CursorShape.SizeBDiagCursor,
                RESIZE_MARGIN,
                RESIZE_MARGIN,
            ),
            0,
            2,
        )
        frame_layout.addWidget(
            self._resize_handle(Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor, RESIZE_MARGIN),
            1,
            0,
        )
        frame_layout.addWidget(content_widget, 1, 1)
        frame_layout.addWidget(
            self._resize_handle(Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor, RESIZE_MARGIN),
            1,
            2,
        )
        frame_layout.addWidget(
            self._resize_handle(
                Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
                Qt.CursorShape.SizeBDiagCursor,
                RESIZE_MARGIN,
                RESIZE_MARGIN,
            ),
            2,
            0,
        )
        frame_layout.addWidget(
            self._resize_handle(
                Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor, None, RESIZE_MARGIN
            ),
            2,
            1,
        )
        frame_layout.addWidget(
            self._resize_handle(
                Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
                Qt.CursorShape.SizeFDiagCursor,
                RESIZE_MARGIN,
                RESIZE_MARGIN,
            ),
            2,
            2,
        )
        frame_layout.setColumnStretch(1, 1)
        frame_layout.setRowStretch(1, 1)

        outer_layout = QVBoxLayout(content_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        outer_layout.addWidget(self.title_bar)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.sidebar = SidebarView(self.service)
        self.matrix = MatrixView(self.service)

        content_layout.addWidget(self.sidebar)
        content_layout.addWidget(self.matrix, 1)

        outer_layout.addLayout(content_layout, 1)

        # Bottom-right resize grip for frameless window
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(RESIZE_MARGIN + 4, RESIZE_MARGIN + 4)
        self.size_grip.setStyleSheet("background: transparent;")
        self._position_size_grip()

    def _resize_handle(
        self,
        edges: Qt.Edge,
        cursor: Qt.CursorShape,
        width: int | None = None,
        height: int | None = None,
    ) -> SystemResizeHandle:
        handle = SystemResizeHandle(self, edges, cursor)
        if width is not None:
            handle.setFixedWidth(width)
        if height is not None:
            handle.setFixedHeight(height)
        return handle

    def start_system_resize(self, edges: Qt.Edge) -> bool:
        window_handle = self.windowHandle()
        if window_handle is None:
            return False
        return window_handle.startSystemResize(edges)

    def _position_size_grip(self) -> None:
        if hasattr(self, "size_grip"):
            self.size_grip.move(
                self.width() - self.size_grip.width(),
                self.height() - self.size_grip.height(),
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_size_grip()

    def refresh_all_views(self) -> None:
        self.sidebar.refresh()
        self.matrix.refresh()

    def show_notification(self, title: str, task_id: str) -> None:
        if self.tray.icon() is None:
            return
        self.tray.showMessage(
            Strings.get("notification_title"),
            Strings.get("notification_body", title=title),
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def show_window(self):
        if self.isMaximized():
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        super().closeEvent(event)
