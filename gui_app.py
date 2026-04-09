from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_config import APP_LOG_PATH, AppConfig, CONFIG_PATH, ensure_runtime_dirs
from controller_factory import build_controller
from database import TaskDB
from flow_runner import FlowRunner
from gui_runner import TaskThreadController
from gui_state import DEFAULT_LOG_PATH, RESULT_FILES
from logger import logger
from result_store import ResultStore
from runtime import RuntimeContext
from utils import generate_strong_password, random_email


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OutlookRegister 控制台")
        self.resize(1120, 780)
        self.task_controller: TaskThreadController | None = None
        self.log_path = DEFAULT_LOG_PATH
        ensure_runtime_dirs()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = QWidget()
        self.log_tab = QWidget()
        self.result_tab = QWidget()
        self.tabs.addTab(self.config_tab, "配置")
        self.tabs.addTab(self.log_tab, "日志")
        self.tabs.addTab(self.result_tab, "结果")

        self._build_config_tab()
        self._build_log_tab()
        self._build_result_tab()
        self._build_menu()
        self._load_config_to_form()
        self._load_log_file()
        self._refresh_result_files()

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

    def _build_config_tab(self) -> None:
        layout = QVBoxLayout(self.config_tab)

        config_group = QGroupBox("基础配置")
        config_form = QFormLayout(config_group)

        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["patchright", "playwright"])
        self.proxy_input = QLineEdit()
        self.proxy_rotation_input = QLineEdit()
        self.bot_wait_input = QSpinBox()
        self.bot_wait_input.setRange(0, 999)
        self.captcha_retry_input = QSpinBox()
        self.captcha_retry_input.setRange(0, 20)
        self.concurrent_input = QSpinBox()
        self.concurrent_input.setRange(1, 100)
        self.max_tasks_input = QSpinBox()
        self.max_tasks_input.setRange(1, 100000)
        self.playwright_path_input = QLineEdit()
        self.ezcaptcha_input = QLineEdit()
        self.sms_activate_input = QLineEdit()

        config_form.addRow("浏览器类型", self.browser_combo)
        config_form.addRow("代理地址", self.proxy_input)
        config_form.addRow("代理轮换 URL", self.proxy_rotation_input)
        config_form.addRow("机器人等待时间(秒)", self.bot_wait_input)
        config_form.addRow("验证码重试次数", self.captcha_retry_input)
        config_form.addRow("并发数", self.concurrent_input)
        config_form.addRow("最大任务数", self.max_tasks_input)
        config_form.addRow("Playwright 浏览器路径", self.playwright_path_input)
        config_form.addRow("EzCaptcha Key", self.ezcaptcha_input)
        config_form.addRow("SmsActivate Key", self.sms_activate_input)

        oauth_group = QGroupBox("OAuth2 配置")
        oauth_form = QFormLayout(oauth_group)
        self.oauth_enabled = QCheckBox("启用 OAuth2")
        self.client_id_input = QLineEdit()
        self.redirect_url_input = QLineEdit()
        self.scopes_input = QTextEdit()
        self.scopes_input.setPlaceholderText("每行一个 Scope")
        self.scopes_input.setFixedHeight(120)

        oauth_form.addRow(self.oauth_enabled)
        oauth_form.addRow("Client ID", self.client_id_input)
        oauth_form.addRow("Redirect URL", self.redirect_url_input)
        oauth_form.addRow("Scopes", self.scopes_input)

        action_layout = QHBoxLayout()
        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载")
        self.prepare_button = QPushButton("准备任务")
        self.start_button = QPushButton("受控启动")
        action_layout.addWidget(self.save_button)
        action_layout.addWidget(self.reload_button)
        action_layout.addWidget(self.prepare_button)
        action_layout.addStretch(1)
        action_layout.addWidget(self.start_button)

        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(config_group)
        layout.addWidget(oauth_group)
        layout.addLayout(action_layout)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.save_button.clicked.connect(self._save_form_to_config)
        self.reload_button.clicked.connect(self._load_config_to_form)
        self.prepare_button.clicked.connect(self._prepare_tasks)
        self.start_button.clicked.connect(self._start_task)

    def _build_log_tab(self) -> None:
        layout = QVBoxLayout(self.log_tab)
        button_layout = QHBoxLayout()
        self.clear_log_button = QPushButton("清空日志窗口")
        self.clear_log_file_button = QPushButton("清空日志文件")
        self.refresh_log_button = QPushButton("刷新日志文件")
        button_layout.addWidget(self.clear_log_button)
        button_layout.addWidget(self.clear_log_file_button)
        button_layout.addWidget(self.refresh_log_button)
        button_layout.addStretch(1)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        layout.addLayout(button_layout)
        layout.addWidget(self.log_output)

        self.clear_log_button.clicked.connect(self.log_output.clear)
        self.clear_log_file_button.clicked.connect(self._clear_log_file)
        self.refresh_log_button.clicked.connect(self._load_log_file)

    def _build_result_tab(self) -> None:
        layout = QVBoxLayout(self.result_tab)
        self.result_views: dict[Path, QPlainTextEdit] = {}

        global_action_layout = QHBoxLayout()
        self.refresh_results_button = QPushButton("刷新全部结果")
        self.clear_all_results_button = QPushButton("清空全部结果")
        global_action_layout.addWidget(self.refresh_results_button)
        global_action_layout.addWidget(self.clear_all_results_button)
        global_action_layout.addStretch(1)
        layout.addLayout(global_action_layout)

        self.refresh_results_button.clicked.connect(self._refresh_result_files)
        self.clear_all_results_button.clicked.connect(self._clear_all_result_files)

        for entry in RESULT_FILES:
            group = QGroupBox(entry.label)
            group_layout = QVBoxLayout(group)

            action_layout = QHBoxLayout()
            refresh_button = QPushButton("刷新")
            clear_button = QPushButton("清空")
            action_layout.addWidget(refresh_button)
            action_layout.addWidget(clear_button)
            action_layout.addStretch(1)

            viewer = QPlainTextEdit()
            viewer.setReadOnly(True)

            group_layout.addLayout(action_layout)
            group_layout.addWidget(viewer)
            layout.addWidget(group)
            self.result_views[entry.path] = viewer

            refresh_button.clicked.connect(
                lambda _checked=False, path=entry.path: self._refresh_single_result_file(path)
            )
            clear_button.clicked.connect(
                lambda _checked=False, path=entry.path: self._clear_single_result_file(path)
            )

        layout.addStretch(1)

    def _choose_config_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择配置文件",
            str(CONFIG_PATH.parent),
            "JSON Files (*.json)",
        )
        if file_path:
            self._load_config_to_form(Path(file_path))

    def _choose_log_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择日志文件",
            str(APP_LOG_PATH.parent),
            "Log Files (*.log *.txt);;All Files (*)",
        )
        if file_path:
            self.log_path = Path(file_path)
            self._load_log_file()

    def _load_config_to_form(self, config_path: Path | None = None) -> None:
        config = AppConfig.load(config_path or CONFIG_PATH)

        self.browser_combo.setCurrentText(config.choose_browser)
        self.proxy_input.setText(config.proxy.url)
        self.proxy_rotation_input.setText(config.proxy.rotation_url)
        self.bot_wait_input.setValue(config.bot_protection_wait)
        self.captcha_retry_input.setValue(config.max_captcha_retries)
        self.concurrent_input.setValue(config.concurrent_flows)
        self.max_tasks_input.setValue(config.max_tasks)
        self.playwright_path_input.setText(config.playwright.browser_path)
        self.ezcaptcha_input.setText(config.api_keys.ezcaptcha)
        self.sms_activate_input.setText(config.api_keys.sms_activate)
        self.oauth_enabled.setChecked(config.oauth2.enable_oauth2)
        self.client_id_input.setText(config.oauth2.client_id)
        self.redirect_url_input.setText(config.oauth2.redirect_url)
        self.scopes_input.setPlainText("\n".join(config.oauth2.scopes))
        self.status_label.setText(f"已加载配置: {config_path or CONFIG_PATH}")

    def _build_config_from_form(self) -> AppConfig:
        scopes = [
            line.strip()
            for line in self.scopes_input.toPlainText().splitlines()
            if line.strip()
        ]
        config = AppConfig.load()
        config.choose_browser = self.browser_combo.currentText()
        config.proxy.url = self.proxy_input.text().strip()
        config.proxy.rotation_url = self.proxy_rotation_input.text().strip()
        config.bot_protection_wait = self.bot_wait_input.value()
        config.max_captcha_retries = self.captcha_retry_input.value()
        config.concurrent_flows = self.concurrent_input.value()
        config.max_tasks = self.max_tasks_input.value()
        config.playwright.browser_path = self.playwright_path_input.text().strip()
        config.api_keys.ezcaptcha = self.ezcaptcha_input.text().strip()
        config.api_keys.sms_activate = self.sms_activate_input.text().strip()
        config.oauth2.enable_oauth2 = self.oauth_enabled.isChecked()
        config.oauth2.client_id = self.client_id_input.text().strip()
        config.oauth2.redirect_url = self.redirect_url_input.text().strip()
        config.oauth2.scopes = scopes
        return config

    def _save_form_to_config(self) -> None:
        config = self._build_config_from_form()
        config.save()
        self.status_label.setText("配置已保存")

    def _append_log(self, text: str) -> None:
        self.log_output.moveCursor(QTextCursor.End)
        self.log_output.insertPlainText(text)
        self.log_output.moveCursor(QTextCursor.End)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(text)

    def _load_log_file(self) -> None:
        if not self.log_path.exists():
            self.log_output.setPlainText("")
            return
        self.log_output.setPlainText(self.log_path.read_text(encoding="utf-8"))

    def _clear_log_file(self) -> None:
        if self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")
        self.log_output.clear()
        self.status_label.setText(f"已清空日志: {self.log_path.name}")

    def _refresh_result_files(self) -> None:
        for path in self.result_views:
            self._refresh_single_result_file(path)

    def _refresh_single_result_file(self, path: Path) -> None:
        viewer = self.result_views[path]
        if path.exists():
            viewer.setPlainText(path.read_text(encoding="utf-8"))
        else:
            viewer.setPlainText("")

    def _clear_single_result_file(self, path: Path) -> None:
        reply = QMessageBox.question(
            self,
            "确认清空",
            f"确认清空结果文件：{path.name} ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        self._refresh_single_result_file(path)
        self.status_label.setText(f"已清空结果文件: {path.name}")

    def _clear_all_result_files(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确认清空全部结果文件吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for path in self.result_views:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        self._refresh_result_files()
        self.status_label.setText("已清空全部结果文件")

    def _prepare_tasks(self) -> None:
        self._save_form_to_config()
        config = AppConfig.load()
        db = TaskDB()
        db.clear_all_tasks()
        for _ in range(config.max_tasks):
            db.create_task(random_email(), generate_strong_password())
        self.status_label.setText(f"已初始化任务库，共 {config.max_tasks} 条")
        logger.info("Task database reinitialized from GUI")

    def _create_task_callable(self):
        def task() -> None:
            config = AppConfig.load()
            db = TaskDB()
            db.reset_in_progress_tasks()
            controller = build_controller(config)
            context = RuntimeContext(config=config, result_store=ResultStore())
            runner = FlowRunner(controller=controller, context=context)

            pending_tasks = db.get_pending_tasks(limit=config.max_tasks)
            if not pending_tasks:
                for _ in range(config.max_tasks):
                    db.create_task(random_email(), generate_strong_password())
                pending_tasks = db.get_pending_tasks(limit=config.max_tasks)

            try:
                success_count = 0
                failed_count = 0
                for task_id, email, password in pending_tasks:
                    db.update_task_status(task_id, "in_progress")
                    if runner.process_single_flow_with_credentials(email, password):
                        db.update_task_status(task_id, "success")
                        success_count += 1
                    else:
                        db.update_task_status(task_id, "failed", "Execution returned False")
                        failed_count += 1

                print(f"\n[Result] - 共: {len(pending_tasks)}, 成功 {success_count}, 失败 {failed_count}")
            finally:
                controller.clean_up(type="all_browser")

        return task

    def _start_task(self) -> None:
        if self.task_controller is not None:
            QMessageBox.information(self, "提示", "已有任务正在执行")
            return

        self._save_form_to_config()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.task_controller = TaskThreadController(self._create_task_callable())
        self.task_controller.log_message.connect(self._append_log)
        self.task_controller.task_finished.connect(self._handle_task_finished)
        self.task_controller.start()
        self.status_label.setText("任务已启动")
        self.tabs.setCurrentWidget(self.log_tab)

    def _handle_task_finished(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "失败", message)
        self.task_controller = None
        self._refresh_result_files()
        self._load_log_file()


def run_gui() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_gui()
