from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QSystemTrayIcon, QWidget, QMenu, QApplication
from PyQt6.QtCore import Qt


from app.config import APP_LOGO_PATH
from app.resources.strings import Strings
from app.services.task_service import TaskService
from app.ui.views.matrix import MatrixView
from app.ui.views.sidebar import SidebarView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(Strings.get("我的任务"))
        self.setWindowIcon(QIcon(APP_LOGO_PATH))
        self.resize(1100, 750)

        self.setWindowFlag(self.windowFlags() | Qt.WindowType.Tool)

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

        layout = QHBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarView(self.service)
        self.matrix = MatrixView(self.service)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.matrix, 1)

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
        self.showNormal()  # 从最小化/隐藏恢复
        self.raise_()  # 提到最前
        self.activateWindow()  # 获取焦点

    def closeEvent(self, event):
        super().closeEvent(event)
