from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
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

        outer_layout = QVBoxLayout(main_widget)
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
