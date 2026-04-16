from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget, QWidget

from app_config import AppConfig, CONFIG_PATH, ConfigValidationError, ensure_runtime_dirs
from gui_config_actions import (
    build_config_from_form,
    choose_config_file,
    get_active_config_path,
    load_config_to_form,
    save_form_to_config,
)
from gui_config_tab import build_config_tab, sync_dynamic_proxy_mode_ui
from gui_console_tab import build_console_tab
from gui_monitor_actions import (
    append_log,
    choose_log_file,
    clear_all_result_files,
    clear_log_file,
    clear_single_result_file,
    export_registered_results,
    format_human_bytes,
    highlight_log_line,
    load_log_file,
    refresh_dashboard_stats,
    refresh_result_files,
    refresh_single_result_file,
)
from gui_oauth_actions import (
    choose_oauth_import_file,
    create_oauth_task_callable,
    export_oauth_success_accounts,
    handle_oauth_task_finished,
    load_oauth_accounts_from_file,
    refresh_oauth_account_summary,
    run_oauth_accounts_gui,
    upload_oauth_success_accounts,
)
from gui_register_actions import (
    create_task_callable,
    create_unique_task,
    handle_task_finished,
    start_task,
    stop_task,
    test_proxy_health,
)
from gui_runner import TaskThreadController
from gui_state import DEFAULT_LOG_PATH


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OutlookRegister 控制台")
        self.resize(1440, 860)
        self.task_controller: TaskThreadController | None = None
        self.oauth_task_controller: TaskThreadController | None = None
        self.log_path = DEFAULT_LOG_PATH
        self.loaded_config_path = CONFIG_PATH
        self.oauth_import_path: Path | None = None
        self.oauth_loaded_accounts = []
        self.oauth_success_accounts = []
        self.oauth_last_results = []
        ensure_runtime_dirs()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._apply_styles()

        self.register_tab = QWidget()
        self.oauth_tab = QWidget()
        self.config_tab = QWidget()
        self.tabs.addTab(self.register_tab, "注册")
        self.tabs.addTab(self.oauth_tab, "OAuth2")
        self.tabs.addTab(self.config_tab, "配置")

        self._build_register_tab()
        self._build_oauth_tab()
        self._build_config_tab()
        self._build_menu()
        self._load_config_to_form(show_popup=False)
        self._load_log_file()
        self._refresh_oauth_account_summary()
        self._refresh_result_files()
        self.tabs.setCurrentWidget(self.register_tab)

        self.result_timer = QTimer(self)
        self.result_timer.timeout.connect(self._refresh_result_files)
        self.result_timer.start(3000)

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("文件")

        open_config_action = QAction("打开配置文件", self)
        open_config_action.triggered.connect(self._choose_config_file)
        menu.addAction(open_config_action)

        open_log_action = QAction("打开日志文件", self)
        open_log_action.triggered.connect(self._choose_log_file)
        menu.addAction(open_log_action)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #0b1120;
                color: #e5eefb;
                font-family: 'Microsoft YaHei UI';
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #1f2a44;
                background: #0f172a;
                border-radius: 16px;
                margin-top: 8px;
            }
            QTabBar::tab {
                background: #162033;
                color: #aebcd2;
                padding: 10px 20px;
                margin-right: 8px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QTabBar::tab:selected {
                background: #2563eb;
                color: white;
            }
            QGroupBox {
                border: 1px solid #24324a;
                border-radius: 16px;
                margin-top: 12px;
                padding: 14px 14px 12px 14px;
                font-weight: 600;
                background-color: #111a2e;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                color: #8ec5ff;
            }
            QLabel[role='heroTitle'] {
                font-size: 24px;
                font-weight: 700;
                color: #f8fbff;
            }
            QLabel[role='heroSubtitle'] {
                color: #94a3b8;
                font-size: 12px;
                padding-bottom: 4px;
            }
            QLabel[role='metricCard'] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1d4ed8, stop:1 #0f766e);
                border: 1px solid #60a5fa;
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                font-size: 13px;
                font-weight: 700;
                min-height: 56px;
            }
            QLabel[role='metricCardAlt'] {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7c3aed, stop:1 #0ea5e9);
                border: 1px solid #93c5fd;
                border-radius: 16px;
                padding: 14px 16px;
                color: white;
                font-size: 13px;
                font-weight: 700;
                min-height: 56px;
            }
            QLabel[role='statusPanel'] {
                background-color: #0d1628;
                border: 1px solid #2d3b55;
                border-radius: 10px;
                padding: 8px 12px;
                color: #e5e7eb;
            }
            QLabel[role='sectionHint'] {
                color: #94a3b8;
                font-size: 12px;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QPlainTextEdit, QTableWidget {
                background-color: #09111f;
                border: 1px solid #2d3b55;
                border-radius: 10px;
                padding: 8px 10px;
                color: #e2e8f0;
                selection-background-color: #2563eb;
                gridline-color: #24324a;
            }
            QHeaderView::section {
                background-color: #162033;
                color: #cfe2ff;
                border: none;
                padding: 8px;
                font-weight: 700;
            }
            QPushButton {
                background-color: #1d4ed8;
                border: none;
                border-radius: 10px;
                padding: 9px 14px;
                color: white;
                font-weight: 600;
                min-width: 88px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #cbd5e1;
            }
            QMenuBar, QMenu {
                background-color: #0b1120;
                color: #e2e8f0;
            }
            QSplitter::handle {
                background-color: #1e293b;
            }
            QSplitter::handle:horizontal {
                width: 6px;
            }
            QSplitter::handle:vertical {
                height: 6px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: #111a2e;
                width: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 24px;
                border-radius: 5px;
            }
            """
        )

    def _build_config_tab(self) -> None:
        build_config_tab(self)

    def _sync_dynamic_proxy_mode_ui(self, mode: str) -> None:
        sync_dynamic_proxy_mode_ui(self, mode)

    def _build_register_tab(self) -> None:
        build_console_tab(self, target_tab=self.register_tab, include_oauth_section=False)

    def _build_oauth_tab(self) -> None:
        build_console_tab(self, target_tab=self.oauth_tab, include_register_section=False)

    def _choose_config_file(self) -> None:
        choose_config_file(self)

    def _choose_log_file(self) -> None:
        choose_log_file(self)

    def _load_config_to_form(self, config_path=None, show_popup: bool = True) -> None:
        load_config_to_form(self, config_path=config_path, show_popup=show_popup)

    def _get_active_config_path(self):
        return get_active_config_path(self)

    def _build_config_from_form(self):
        return build_config_from_form(self)

    def _save_form_to_config(self, show_popup: bool = True) -> bool:
        return save_form_to_config(self, show_popup=show_popup)

    def _highlight_log_line(self, text: str) -> None:
        highlight_log_line(self, text)

    def _append_log(self, text: str) -> None:
        append_log(self, text)

    def _load_log_file(self) -> None:
        load_log_file(self)

    def _clear_log_file(self) -> None:
        clear_log_file(self)

    def _format_human_bytes(self, size: int) -> str:
        return format_human_bytes(self, size)

    def _refresh_dashboard_stats(self) -> None:
        refresh_dashboard_stats(self)

    def _refresh_result_files(self) -> None:
        refresh_result_files(self)

    def _refresh_single_result_file(self, path) -> None:
        refresh_single_result_file(self, path)

    def _clear_single_result_file(self, path) -> None:
        clear_single_result_file(self, path)

    def _clear_all_result_files(self) -> None:
        clear_all_result_files(self)

    def _export_registered_results(self) -> None:
        export_registered_results(self)

    def _test_proxy_health(self) -> None:
        test_proxy_health(self)

    def _create_unique_task(self, db, max_attempts: int = 200) -> bool:
        return create_unique_task(self, db, max_attempts=max_attempts)

    def _create_task_callable(self):
        return create_task_callable(self)

    def _start_task(self, show_popup: bool = False) -> None:
        start_task(self, show_popup=show_popup)

    def _stop_task(self) -> None:
        stop_task(self)

    def _handle_task_finished(self, success: bool, message: str) -> None:
        handle_task_finished(self, success, message)

    def _choose_oauth_import_file(self) -> None:
        choose_oauth_import_file(self)

    def _load_oauth_accounts_from_file(self) -> None:
        load_oauth_accounts_from_file(self)

    def _refresh_oauth_account_summary(self) -> None:
        refresh_oauth_account_summary(self)

    def _create_oauth_task_callable(self):
        return create_oauth_task_callable(self)

    def _run_oauth_accounts(self) -> None:
        run_oauth_accounts_gui(self)

    def _export_oauth_success_accounts(self) -> None:
        export_oauth_success_accounts(self)

    def _upload_oauth_success_accounts(self) -> None:
        upload_oauth_success_accounts(self)

    def _handle_oauth_task_finished(self, success: bool, message: str) -> None:
        handle_oauth_task_finished(self, success, message)


def run_gui() -> None:
    app = QApplication([])
    try:
        AppConfig.load().validate()
    except ConfigValidationError as exc:
        QMessageBox.warning(None, "配置校验失败", "\n".join(exc.errors))
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_gui()
