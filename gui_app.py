from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_config import APP_LOG_PATH, AppConfig, CONFIG_PATH, ConfigValidationError, ensure_runtime_dirs
from controller_factory import build_controller
from database import TaskDB
from execution_models import ErrorCode, FlowResult, RiskCircuitBreaker, Stage
from flow_runner import FlowRunner
from gui_runner import TaskThreadController
from gui_state import DEFAULT_LOG_PATH, RESULT_FILES
from logger import logger
from result_store import ResultStore
from runtime import RuntimeContext
from services import ProxyManager
from utils import generate_strong_password, random_email


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OutlookRegister 控制台")
        self.resize(1440, 860)
        self.task_controller: TaskThreadController | None = None
        self.log_path = DEFAULT_LOG_PATH
        ensure_runtime_dirs()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self._apply_styles()

        self.console_tab = QWidget()
        self.config_tab = QWidget()
        self.tabs.addTab(self.console_tab, "控制台")
        self.tabs.addTab(self.config_tab, "配置")

        self._build_console_tab()
        self._build_config_tab()
        self._build_menu()
        self._load_config_to_form()
        self._load_log_file()
        self._refresh_result_files()
        self.tabs.setCurrentWidget(self.console_tab)

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
        outer_layout = QVBoxLayout(self.config_tab)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        root_layout = QVBoxLayout(content)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(12)

        hero_group = QGroupBox("配置中心")
        hero_layout = QVBoxLayout(hero_group)
        hero_layout.setSpacing(8)
        hero_title = QLabel("Configuration Workspace")
        hero_title.setProperty("role", "heroTitle")
        hero_subtitle = QLabel("仅负责浏览器、代理、并发、风控、邮箱后缀和 OAuth2 参数配置，不承载执行控制与日志结果。")
        hero_subtitle.setProperty("role", "heroSubtitle")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)

        helper_group = QGroupBox("配置操作")
        helper_layout = QHBoxLayout(helper_group)
        helper_layout.setSpacing(10)
        self.save_button = QPushButton("保存配置")
        self.reload_button = QPushButton("重新加载")
        self.prepare_button = QPushButton("准备任务")
        helper_layout.addWidget(self.save_button)
        helper_layout.addWidget(self.reload_button)
        helper_layout.addWidget(self.prepare_button)
        helper_layout.addStretch(1)

        content_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        config_group = QGroupBox("基础配置")
        config_form = QFormLayout(config_group)
        config_form.setSpacing(10)
        config_form.setLabelAlignment(Qt.AlignLeft)
        config_form.setFormAlignment(Qt.AlignTop)

        browser_group = QGroupBox("浏览器配置")
        browser_form = QFormLayout(browser_group)
        browser_form.setSpacing(10)
        browser_form.setLabelAlignment(Qt.AlignLeft)
        browser_form.setFormAlignment(Qt.AlignTop)

        proxy_group = QGroupBox("代理与网络")
        proxy_form = QFormLayout(proxy_group)
        proxy_form.setSpacing(10)
        proxy_form.setLabelAlignment(Qt.AlignLeft)
        proxy_form.setFormAlignment(Qt.AlignTop)

        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["patchright", "playwright"])
        self.email_domain_combo = QComboBox()
        self.email_domain_combo.addItems(["hotmail.com", "outlook.com"])
        self.proxy_input = QLineEdit()
        self.route_intercept_enabled = QCheckBox("启用路由拦截(节省代理流量)")
        self.headless_enabled = QCheckBox("启用无头浏览器")
        self.bot_wait_input = QSpinBox()
        self.bot_wait_input.setRange(0, 999)
        self.captcha_retry_input = QSpinBox()
        self.captcha_retry_input.setRange(0, 20)
        self.concurrent_input = QSpinBox()
        self.concurrent_input.setRange(1, 100)
        self.max_tasks_input = QSpinBox()
        self.max_tasks_input.setRange(1, 100000)
        self.max_browsers_input = QSpinBox()
        self.max_browsers_input.setRange(1, 100)
        self.playwright_path_input = QLineEdit()
        self.ezcaptcha_input = QLineEdit()
        self.sms_activate_input = QLineEdit()
        self.max_risk_input = QSpinBox()
        self.max_risk_input.setRange(1, 50)
        self.max_failure_streak_input = QSpinBox()
        self.max_failure_streak_input.setRange(1, 100)
        self.max_task_duration_input = QSpinBox()
        self.max_task_duration_input.setRange(10, 3600)
        self.max_sms_wait_cycles_input = QSpinBox()
        self.max_sms_wait_cycles_input.setRange(1, 120)

        browser_form.addRow("浏览器类型", self.browser_combo)
        browser_form.addRow(self.headless_enabled)
        browser_form.addRow("Playwright 浏览器路径", self.playwright_path_input)
        browser_form.addRow("浏览器池大小", self.max_browsers_input)

        proxy_form.addRow("静态代理地址", self.proxy_input)

        config_form.addRow("邮箱后缀", self.email_domain_combo)
        config_form.addRow("机器人等待时间(秒)", self.bot_wait_input)
        config_form.addRow("验证码重试次数", self.captcha_retry_input)
        config_form.addRow("并发数", self.concurrent_input)
        config_form.addRow("最大任务数", self.max_tasks_input)
        config_form.addRow("EzCaptcha Key", self.ezcaptcha_input)
        config_form.addRow("SmsActivate Key", self.sms_activate_input)
        config_form.addRow("连续风险熔断阈值", self.max_risk_input)
        config_form.addRow("连续失败熔断阈值", self.max_failure_streak_input)
        config_form.addRow("单任务最大时长(秒)", self.max_task_duration_input)
        config_form.addRow("短信轮询次数上限", self.max_sms_wait_cycles_input)

        oauth_group = QGroupBox("OAuth2 配置")
        oauth_form = QFormLayout(oauth_group)
        oauth_form.setSpacing(10)
        oauth_form.setLabelAlignment(Qt.AlignLeft)
        oauth_form.setFormAlignment(Qt.AlignTop)
        self.oauth_enabled = QCheckBox("启用 OAuth2")
        self.client_id_input = QLineEdit()
        self.redirect_url_input = QLineEdit()
        self.scopes_input = QTextEdit()
        self.scopes_input.setPlaceholderText("每行一个 Scope")
        self.scopes_input.setFixedHeight(180)
        oauth_form.addRow(self.oauth_enabled)
        oauth_form.addRow("Client ID", self.client_id_input)
        oauth_form.addRow("Redirect URL", self.redirect_url_input)
        oauth_form.addRow("Scopes", self.scopes_input)

        dynamic_proxy_group = QGroupBox("动态住宅代理与流量优化")
        dynamic_proxy_form = QFormLayout(dynamic_proxy_group)
        dynamic_proxy_form.setSpacing(10)
        dynamic_proxy_form.setLabelAlignment(Qt.AlignLeft)
        dynamic_proxy_form.setFormAlignment(Qt.AlignTop)
        self.dynamic_proxy_enabled = QCheckBox("启用动态住宅代理")
        self.dynamic_proxy_provider_input = QLineEdit()
        self.dynamic_proxy_provider_input.setPlaceholderText("例如：IPFoxy")
        self.dynamic_proxy_endpoint_input = QLineEdit()
        self.dynamic_proxy_endpoint_input.setPlaceholderText("例如：gate.ipfoxy.com:12345")
        self.dynamic_proxy_username_input = QLineEdit()
        self.dynamic_proxy_username_input.setPlaceholderText("IPFoxy 用户名")
        self.dynamic_proxy_password_input = QLineEdit()
        self.dynamic_proxy_password_input.setEchoMode(QLineEdit.Password)
        self.dynamic_proxy_password_input.setPlaceholderText("IPFoxy 密码")
        self.dynamic_proxy_country_input = QLineEdit()
        self.dynamic_proxy_country_input.setPlaceholderText("可选，例如：us")
        self.dynamic_proxy_session_input = QLineEdit()
        self.dynamic_proxy_session_input.setPlaceholderText("可选，会话标识")
        self.dynamic_proxy_sticky_minutes_input = QSpinBox()
        self.dynamic_proxy_sticky_minutes_input.setRange(1, 10080)
        self.dynamic_proxy_sticky_minutes_input.setValue(30)
        dynamic_proxy_form.addRow(self.dynamic_proxy_enabled)
        dynamic_proxy_form.addRow("代理服务商", self.dynamic_proxy_provider_input)
        dynamic_proxy_form.addRow("代理入口", self.dynamic_proxy_endpoint_input)
        dynamic_proxy_form.addRow("代理用户名", self.dynamic_proxy_username_input)
        dynamic_proxy_form.addRow("代理密码", self.dynamic_proxy_password_input)
        dynamic_proxy_form.addRow("国家代码", self.dynamic_proxy_country_input)
        dynamic_proxy_form.addRow("会话标识", self.dynamic_proxy_session_input)
        dynamic_proxy_form.addRow("粘性时长(分钟)", self.dynamic_proxy_sticky_minutes_input)
        dynamic_proxy_form.addRow(self.route_intercept_enabled)
        dynamic_proxy_hint = QLabel("动态住宅代理与路由拦截都属于代理流量策略，建议在这里统一配置。路由拦截当前仅阻止 image / media / font。")
        dynamic_proxy_hint.setWordWrap(True)
        dynamic_proxy_hint.setProperty("role", "sectionHint")
        dynamic_proxy_form.addRow(dynamic_proxy_hint)

        config_hint_group = QGroupBox("使用说明")
        config_hint_layout = QVBoxLayout(config_hint_group)
        config_hint = QLabel(
            "建议先完成配置保存，再切换到控制台启动任务。邮箱后缀会同时影响注册页域名选择、结果文件保存格式和 OAuth 登录邮箱地址。"
        )
        config_hint.setWordWrap(True)
        config_hint.setProperty("role", "sectionHint")
        config_hint_layout.addWidget(config_hint)

        left_layout.addWidget(browser_group)
        left_layout.addWidget(proxy_group)
        left_layout.addWidget(config_group)
        left_layout.addWidget(config_hint_group)
        left_layout.addStretch(1)

        right_layout.addWidget(oauth_group)
        right_layout.addWidget(dynamic_proxy_group)
        right_layout.addStretch(1)

        content_splitter.addWidget(left_panel)
        content_splitter.addWidget(right_panel)
        content_splitter.setSizes([900, 520])

        root_layout.addWidget(hero_group)
        root_layout.addWidget(helper_group)
        root_layout.addWidget(content_splitter)

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

        self.save_button.clicked.connect(self._save_form_to_config)
        self.reload_button.clicked.connect(self._load_config_to_form)
        self.prepare_button.clicked.connect(self._prepare_tasks)

    def _build_console_tab(self) -> None:
        outer_layout = QVBoxLayout(self.console_tab)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        root_layout = QVBoxLayout(content)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(12)
        self.result_views: dict[Path, QPlainTextEdit] = {}

        hero_group = QGroupBox("控制台")
        hero_layout = QVBoxLayout(hero_group)
        hero_layout.setSpacing(8)
        hero_title = QLabel("Execution Console")
        hero_title.setProperty("role", "heroTitle")
        hero_subtitle = QLabel("集中进行任务启停、状态观测、日志追踪、任务详情与结果文件查看。")
        hero_subtitle.setProperty("role", "heroSubtitle")
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)

        overview_group = QGroupBox("运行总览")
        overview_layout = QGridLayout(overview_group)
        overview_layout.setHorizontalSpacing(10)
        overview_layout.setVerticalSpacing(10)
        self.metric_status_card = QLabel("运行状态\n待命")
        self.metric_status_card.setProperty("role", "metricCard")
        self.metric_tasks_card = QLabel("任务池\n待执行 0 / 运行中 0")
        self.metric_tasks_card.setProperty("role", "metricCardAlt")
        self.metric_success_card = QLabel("成功 / 失败\n0 / 0")
        self.metric_success_card.setProperty("role", "metricCard")
        self.metric_risk_card = QLabel("风险监控\n正常")
        self.metric_risk_card.setProperty("role", "metricCardAlt")
        overview_layout.addWidget(self.metric_status_card, 0, 0)
        overview_layout.addWidget(self.metric_tasks_card, 0, 1)
        overview_layout.addWidget(self.metric_success_card, 0, 2)
        overview_layout.addWidget(self.metric_risk_card, 0, 3)

        console_panel = QWidget()
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(12)

        control_group = QGroupBox("任务控制")
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(10)
        control_hint = QLabel("控制台负责启动、停止、风险观测和执行结果查看。")
        control_hint.setProperty("role", "sectionHint")
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.risk_status_label = QLabel("风险状态：正常")
        self.failure_stats_label = QLabel("最近失败：无")
        self.status_label.setProperty("role", "statusPanel")
        self.risk_status_label.setProperty("role", "statusPanel")
        self.failure_stats_label.setProperty("role", "statusPanel")

        primary_action_layout = QHBoxLayout()
        primary_action_layout.setSpacing(10)
        self.start_button = QPushButton("启动任务")
        self.stop_button = QPushButton("停止任务")
        self.stop_button.setEnabled(False)
        self.refresh_tasks_button = QPushButton("刷新任务")
        primary_action_layout.addWidget(self.start_button)
        primary_action_layout.addWidget(self.stop_button)
        primary_action_layout.addWidget(self.refresh_tasks_button)
        primary_action_layout.addStretch(1)

        secondary_action_layout = QHBoxLayout()
        secondary_action_layout.setSpacing(10)
        self.refresh_log_button = QPushButton("刷新日志")
        self.clear_log_button = QPushButton("清空日志窗口")
        self.clear_log_file_button = QPushButton("清空日志文件")
        self.refresh_results_button = QPushButton("刷新结果")
        self.test_proxy_button = QPushButton("测试代理")
        self.clear_all_results_button = QPushButton("清空全部结果")
        secondary_action_layout.addWidget(self.refresh_log_button)
        secondary_action_layout.addWidget(self.clear_log_button)
        secondary_action_layout.addWidget(self.clear_log_file_button)
        secondary_action_layout.addWidget(self.refresh_results_button)
        secondary_action_layout.addWidget(self.test_proxy_button)
        secondary_action_layout.addWidget(self.clear_all_results_button)

        control_layout.addWidget(control_hint)
        control_layout.addWidget(self.status_label)
        control_layout.addWidget(self.risk_status_label)
        control_layout.addWidget(self.failure_stats_label)
        control_layout.addLayout(primary_action_layout)
        control_layout.addLayout(secondary_action_layout)

        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("运行日志将在此实时显示…")
        self.log_output.setMinimumHeight(180)
        self.log_output.setMaximumHeight(240)
        log_layout.addWidget(self.log_output)

        monitor_group = QGroupBox("任务监控")
        monitor_layout = QVBoxLayout(monitor_group)
        monitor_layout.setSpacing(10)
        monitor_hint = QLabel("展示最近任务状态、阶段、错误码与风控命中情况，并支持重跑失败任务。")
        monitor_hint.setProperty("role", "sectionHint")

        task_toolbar = QHBoxLayout()
        self.task_filter_combo = QComboBox()
        self.task_filter_combo.addItems(["all", "failed", "success", "in_progress", "pending", "risk"])
        self.task_filter_combo.setCurrentText("all")
        self.retry_selected_button = QPushButton("重跑选中任务")
        self.retry_failed_button = QPushButton("重跑全部失败任务")
        task_toolbar.addWidget(QLabel("筛选："))
        task_toolbar.addWidget(self.task_filter_combo)
        task_toolbar.addWidget(self.retry_selected_button)
        task_toolbar.addWidget(self.retry_failed_button)
        task_toolbar.addStretch(1)

        self.task_table = QTableWidget(0, 7)
        self.task_table.setHorizontalHeaderLabels(["任务ID", "邮箱", "状态", "阶段", "错误码", "风险", "更新时间"])
        self.task_table.verticalHeader().setVisible(False)
        self.task_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.task_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.task_table.setMinimumHeight(280)
        self.task_table.itemSelectionChanged.connect(self._refresh_selected_task_detail)

        detail_group = QGroupBox("任务详情")
        detail_layout = QVBoxLayout(detail_group)
        self.task_detail_view = QPlainTextEdit()
        self.task_detail_view.setReadOnly(True)
        self.task_detail_view.setPlaceholderText("选择上方任务后，这里将显示详细状态、阶段与错误信息。")
        self.task_detail_view.setMinimumHeight(120)
        self.task_detail_view.setMaximumHeight(180)
        detail_layout.addWidget(self.task_detail_view)

        monitor_layout.addWidget(monitor_hint)
        monitor_layout.addLayout(task_toolbar)
        monitor_layout.addWidget(self.task_table)

        analytics_group = QGroupBox("阶段级统计")
        analytics_layout = QGridLayout(analytics_group)
        analytics_layout.setHorizontalSpacing(10)
        analytics_layout.setVerticalSpacing(10)
        self.metric_register_rate_card = QLabel("注册成功率\n0%")
        self.metric_register_rate_card.setProperty("role", "metricCard")
        self.metric_oauth_rate_card = QLabel("OAuth 成功率\n0%")
        self.metric_oauth_rate_card.setProperty("role", "metricCardAlt")
        self.metric_avg_duration_card = QLabel("平均耗时\n0 ms")
        self.metric_avg_duration_card.setProperty("role", "metricCard")
        self.metric_risk_count_card = QLabel("风控次数\n0")
        self.metric_risk_count_card.setProperty("role", "metricCardAlt")
        self.metric_total_traffic_card = QLabel("总流量\n0 B / 0 B")
        self.metric_total_traffic_card.setProperty("role", "metricCard")
        self.metric_avg_traffic_card = QLabel("平均流量\n0 B / 0 B")
        self.metric_avg_traffic_card.setProperty("role", "metricCardAlt")
        self.metric_blocked_card = QLabel("资源拦截\n0 / 0.0")
        self.metric_blocked_card.setProperty("role", "metricCard")
        analytics_layout.addWidget(self.metric_register_rate_card, 0, 0)
        analytics_layout.addWidget(self.metric_oauth_rate_card, 0, 1)
        analytics_layout.addWidget(self.metric_avg_duration_card, 0, 2)
        analytics_layout.addWidget(self.metric_risk_count_card, 0, 3)
        analytics_layout.addWidget(self.metric_total_traffic_card, 1, 0)
        analytics_layout.addWidget(self.metric_avg_traffic_card, 1, 1)
        analytics_layout.addWidget(self.metric_blocked_card, 1, 2)
        self.error_distribution_view = QPlainTextEdit()
        self.error_distribution_view.setReadOnly(True)
        self.error_distribution_view.setPlaceholderText("最近 100 个任务错误分布将在此显示…")
        self.error_distribution_view.setMinimumHeight(120)
        analytics_layout.addWidget(self.error_distribution_view, 2, 0, 1, 4)

        results_group = QGroupBox("结果中心")
        results_layout = QVBoxLayout(results_group)
        results_layout.setSpacing(10)

        result_header_layout = QHBoxLayout()
        result_header_hint = QLabel("所有结果文件集中显示，可直接刷新或清空单个结果。")
        result_header_hint.setProperty("role", "sectionHint")
        result_header_layout.addWidget(result_header_hint)
        result_header_layout.addStretch(1)
        results_layout.addLayout(result_header_layout)

        result_columns = QVBoxLayout()
        result_columns.setSpacing(10)

        for entry in RESULT_FILES:
            group = QGroupBox(entry.label)
            group_layout = QVBoxLayout(group)
            group_layout.setSpacing(8)

            action_layout = QHBoxLayout()
            refresh_button = QPushButton("刷新")
            clear_button = QPushButton("清空")
            action_layout.addWidget(refresh_button)
            action_layout.addWidget(clear_button)
            action_layout.addStretch(1)

            viewer = QPlainTextEdit()
            viewer.setReadOnly(True)
            viewer.setPlaceholderText(f"{entry.label} 暂无内容")
            viewer.setMinimumHeight(150)

            group_layout.addLayout(action_layout)
            group_layout.addWidget(viewer)
            self.result_views[entry.path] = viewer

            refresh_button.clicked.connect(
                lambda _checked=False, path=entry.path: self._refresh_single_result_file(path)
            )
            clear_button.clicked.connect(
                lambda _checked=False, path=entry.path: self._clear_single_result_file(path)
            )

            result_columns.addWidget(group)

        result_columns.addStretch(1)
        results_layout.addLayout(result_columns)

        top_row_splitter = QSplitter(Qt.Horizontal)
        top_row_splitter.addWidget(control_group)
        top_row_splitter.addWidget(monitor_group)
        top_row_splitter.setChildrenCollapsible(False)
        top_row_splitter.setSizes([720, 720])

        middle_row_splitter = QSplitter(Qt.Horizontal)
        middle_row_splitter.addWidget(log_group)
        middle_row_splitter.addWidget(detail_group)
        middle_row_splitter.setChildrenCollapsible(False)
        middle_row_splitter.setSizes([720, 720])

        console_layout.addWidget(top_row_splitter)
        console_layout.addWidget(middle_row_splitter)
        console_layout.addWidget(analytics_group)
        console_layout.addWidget(results_group)
        console_layout.addStretch(1)

        root_layout.addWidget(hero_group)
        root_layout.addWidget(overview_group)
        root_layout.addWidget(console_panel)

        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

        self.start_button.clicked.connect(self._start_task)
        self.stop_button.clicked.connect(self._stop_task)
        self.clear_log_button.clicked.connect(self.log_output.clear)
        self.clear_log_file_button.clicked.connect(self._clear_log_file)
        self.refresh_log_button.clicked.connect(self._load_log_file)
        self.refresh_results_button.clicked.connect(self._refresh_result_files)
        self.test_proxy_button.clicked.connect(self._test_proxy_health)
        self.clear_all_results_button.clicked.connect(self._clear_all_result_files)
        self.task_filter_combo.currentTextChanged.connect(self._refresh_task_table)
        self.refresh_tasks_button.clicked.connect(self._refresh_task_table)
        self.retry_selected_button.clicked.connect(self._retry_selected_task)
        self.retry_failed_button.clicked.connect(self._retry_failed_tasks)

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

    def _load_config_to_form(self, config_path: Path | None = None, show_popup: bool = True) -> None:
        config = AppConfig.load(config_path or CONFIG_PATH)

        self.browser_combo.setCurrentText(config.choose_browser)
        self.email_domain_combo.setCurrentText(config.email_domain)
        self.proxy_input.setText(config.proxy.url)
        self.route_intercept_enabled.setChecked(config.proxy.enable_route_intercept)
        self.headless_enabled.setChecked(config.playwright.headless)
        self.bot_wait_input.setValue(config.bot_protection_wait)
        self.captcha_retry_input.setValue(config.max_captcha_retries)
        self.concurrent_input.setValue(config.concurrent_flows)
        self.max_tasks_input.setValue(config.max_tasks)
        self.max_browsers_input.setValue(config.browser_pool.max_browsers)
        self.playwright_path_input.setText(config.playwright.browser_path)
        self.ezcaptcha_input.setText(config.api_keys.ezcaptcha)
        self.sms_activate_input.setText(config.api_keys.sms_activate)
        self.max_risk_input.setValue(config.risk_control.max_consecutive_risk)
        self.max_failure_streak_input.setValue(config.risk_control.max_failure_streak)
        self.max_task_duration_input.setValue(config.risk_control.max_task_duration_seconds)
        self.max_sms_wait_cycles_input.setValue(config.risk_control.max_sms_wait_cycles)
        self.oauth_enabled.setChecked(config.oauth2.enable_oauth2)
        self.client_id_input.setText(config.oauth2.client_id)
        self.redirect_url_input.setText(config.oauth2.redirect_url)
        self.scopes_input.setPlainText("\n".join(config.oauth2.scopes))
        self.dynamic_proxy_enabled.setChecked(config.oauth2.dynamic_residential_proxy.enabled)
        self.dynamic_proxy_provider_input.setText(config.oauth2.dynamic_residential_proxy.provider)
        self.dynamic_proxy_endpoint_input.setText(config.oauth2.dynamic_residential_proxy.endpoint)
        self.dynamic_proxy_username_input.setText(config.oauth2.dynamic_residential_proxy.username)
        self.dynamic_proxy_password_input.setText(config.oauth2.dynamic_residential_proxy.password)
        self.dynamic_proxy_country_input.setText(config.oauth2.dynamic_residential_proxy.country)
        self.dynamic_proxy_session_input.setText(config.oauth2.dynamic_residential_proxy.session)
        self.dynamic_proxy_sticky_minutes_input.setValue(config.oauth2.dynamic_residential_proxy.sticky_minutes)
        self.status_label.setText(f"已加载配置: {config_path or CONFIG_PATH}")
        if show_popup:
            QMessageBox.information(self, "重新加载完成", f"已重新加载配置:\n{config_path or CONFIG_PATH}")

    def _build_config_from_form(self) -> AppConfig:
        scopes = [
            line.strip()
            for line in self.scopes_input.toPlainText().splitlines()
            if line.strip()
        ]
        config = AppConfig.load()
        config.choose_browser = self.browser_combo.currentText()
        config.email_domain = self.email_domain_combo.currentText().strip().lower()
        config.proxy.url = self.proxy_input.text().strip()
        config.proxy.rotation_url = ""
        config.proxy.enable_route_intercept = self.route_intercept_enabled.isChecked()
        config.bot_protection_wait = self.bot_wait_input.value()
        config.max_captcha_retries = self.captcha_retry_input.value()
        config.concurrent_flows = self.concurrent_input.value()
        config.max_tasks = self.max_tasks_input.value()
        config.browser_pool.max_browsers = self.max_browsers_input.value()
        config.playwright.browser_path = self.playwright_path_input.text().strip()
        config.playwright.headless = self.headless_enabled.isChecked()
        config.api_keys.ezcaptcha = self.ezcaptcha_input.text().strip()
        config.api_keys.sms_activate = self.sms_activate_input.text().strip()
        config.risk_control.max_consecutive_risk = self.max_risk_input.value()
        config.risk_control.max_failure_streak = self.max_failure_streak_input.value()
        config.risk_control.max_task_duration_seconds = self.max_task_duration_input.value()
        config.risk_control.max_sms_wait_cycles = self.max_sms_wait_cycles_input.value()
        config.oauth2.enable_oauth2 = self.oauth_enabled.isChecked()
        config.oauth2.client_id = self.client_id_input.text().strip()
        config.oauth2.redirect_url = self.redirect_url_input.text().strip()
        config.oauth2.scopes = scopes
        config.oauth2.dynamic_residential_proxy.enabled = self.dynamic_proxy_enabled.isChecked()
        config.oauth2.dynamic_residential_proxy.provider = self.dynamic_proxy_provider_input.text().strip() or "IPFoxy"
        config.oauth2.dynamic_residential_proxy.endpoint = self.dynamic_proxy_endpoint_input.text().strip()
        config.oauth2.dynamic_residential_proxy.username = self.dynamic_proxy_username_input.text().strip()
        config.oauth2.dynamic_residential_proxy.password = self.dynamic_proxy_password_input.text().strip()
        config.oauth2.dynamic_residential_proxy.country = self.dynamic_proxy_country_input.text().strip()
        config.oauth2.dynamic_residential_proxy.session = self.dynamic_proxy_session_input.text().strip()
        config.oauth2.dynamic_residential_proxy.sticky_minutes = self.dynamic_proxy_sticky_minutes_input.value()
        return config

    def _save_form_to_config(self, show_popup: bool = True) -> bool:
        config = self._build_config_from_form()
        try:
            config.validate()
        except ConfigValidationError as exc:
            QMessageBox.warning(self, "配置校验失败", "\n".join(exc.errors))
            self.status_label.setText("配置校验失败")
            return False

        config.save()
        if show_popup:
            QMessageBox.information(self, "保存成功", f"配置已保存到:\n{CONFIG_PATH}")
        self.status_label.setText("配置已保存")
        return True

    def _highlight_log_line(self, text: str) -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        line_format = QTextCharFormat()
        if "ERROR" in text:
            line_format.setForeground(QColor("#f87171"))
        elif "WARNING" in text or "警告" in text:
            line_format.setForeground(QColor("#fbbf24"))
        elif "INFO" in text:
            line_format.setForeground(QColor("#93c5fd"))
        else:
            line_format.setForeground(QColor("#e2e8f0"))
        cursor.insertText(text, line_format)
        self.log_output.setTextCursor(cursor)
        self.log_output.ensureCursorVisible()

    def _append_log(self, text: str) -> None:
        self._highlight_log_line(text)
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(text)

    def _load_log_file(self) -> None:
        if not self.log_path.exists():
            self.log_output.setPlainText("")
            return
        self.log_output.setPlainText("")
        for line in self.log_path.read_text(encoding="utf-8").splitlines(True):
            self._highlight_log_line(line)

    def _clear_log_file(self) -> None:
        if self.log_path.exists():
            self.log_path.write_text("", encoding="utf-8")
        self.log_output.clear()
        self.status_label.setText(f"已清空日志: {self.log_path.name}")

    def _status_color(self, status: str) -> QColor:
        return {
            "success": QColor("#22c55e"),
            "failed": QColor("#ef4444"),
            "in_progress": QColor("#38bdf8"),
            "pending": QColor("#94a3b8"),
            "reserved": QColor("#f59e0b"),
        }.get(status, QColor("#e2e8f0"))

    def _refresh_task_table(self) -> None:
        db = TaskDB()
        tasks = db.get_recent_tasks(limit=30, status_filter=self.task_filter_combo.currentText())
        self.task_table.setRowCount(len(tasks))
        for row_index, task in enumerate(tasks):
            for column_index, value in enumerate(task):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setForeground(self._status_color(str(value)))
                if column_index == 5 and str(value) == "1":
                    item.setForeground(QColor("#fbbf24"))
                    item.setText("是")
                elif column_index == 5:
                    item.setText("否")
                self.task_table.setItem(row_index, column_index, item)
        self.task_table.resizeColumnsToContents()
        if tasks and self.task_table.currentRow() < 0:
            self.task_table.selectRow(0)
            self._refresh_selected_task_detail()
        elif not tasks:
            self.task_detail_view.setPlainText("")

    def _refresh_selected_task_detail(self) -> None:
        selected_items = self.task_table.selectedItems()
        if not selected_items:
            return
        task_id_text = selected_items[0].text()
        if not task_id_text.isdigit():
            return
        db = TaskDB()
        detail = db.get_task_detail(int(task_id_text))
        if not detail:
            self.task_detail_view.setPlainText("")
            return
        lines = [f"{key}: {value}" for key, value in detail.items()]
        self.task_detail_view.setPlainText("\n".join(lines))

    def _retry_selected_task(self) -> None:
        selected_items = self.task_table.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先选择一个任务")
            return
        task_id_text = selected_items[0].text()
        if not task_id_text.isdigit():
            return
        task_id = int(task_id_text)
        db = TaskDB()
        detail = db.get_task_detail(task_id)
        if not detail:
            return
        if detail.get("status") != "failed":
            QMessageBox.information(self, "提示", "仅支持重跑失败任务")
            return
        if self.task_controller is not None:
            QMessageBox.information(self, "提示", "当前已有任务在执行，请等待当前批次完成后再重跑")
            return

        db.reset_task_to_pending(task_id)
        retry_mode = detail.get("retry_mode", "full")
        mode_label = "仅 OAuth" if retry_mode == "oauth_only" else "全流程"
        self._refresh_result_files()
        self.status_label.setText(f"任务 {task_id} 已重置并开始重跑（{mode_label}）")
        self._start_task(show_popup=False)

    def _retry_failed_tasks(self) -> None:
        if self.task_controller is not None:
            QMessageBox.information(self, "提示", "当前已有任务在执行，请等待当前批次完成后再重跑")
            return

        db = TaskDB()
        count = db.reset_failed_tasks_to_pending()
        if count <= 0:
            QMessageBox.information(self, "提示", "当前没有失败任务可重跑")
            self.status_label.setText("当前没有失败任务可重跑")
            return

        self._refresh_result_files()
        self.status_label.setText(f"已重置 {count} 条失败任务，并已开始自动重跑")
        self._start_task(show_popup=False)

    def _refresh_risk_status(self) -> None:
        db = TaskDB()
        stats = db.get_stats()
        failures = db.get_recent_failure_stats(limit=10)
        failed = stats.get("failed", 0)
        running = stats.get("in_progress", 0)
        success = stats.get("success", 0)
        pending = stats.get("pending", 0)

        self.metric_status_card.setText(f"运行状态\n{'运行中' if running else '待命'}")
        self.metric_tasks_card.setText(f"任务池\n待执行 {pending} / 运行中 {running}")
        self.metric_success_card.setText(f"成功 / 失败\n{success} / {failed}")
        self.metric_risk_card.setText(f"风险监控\n{'关注' if failed else '正常'}")

        self.risk_status_label.setText(f"风险状态：失败任务 {failed}，运行中 {running}，待处理 {pending}")
        if failures:
            summary = ", ".join(f"{code}:{count}" for code, count in sorted(failures.items()))
            self.failure_stats_label.setText(f"最近失败：{summary}")
        else:
            self.failure_stats_label.setText("最近失败：无")

    def _format_human_bytes(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        value = float(max(0, size))
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{value:.2f} GB"

    def _refresh_dashboard_stats(self) -> None:
        stats = ResultStore().get_dashboard_stats(recent_limit=100)
        self.metric_register_rate_card.setText(f"注册成功率\n{stats['register_success_rate']}%")
        self.metric_oauth_rate_card.setText(f"OAuth 成功率\n{stats['oauth_success_rate']}%")
        self.metric_avg_duration_card.setText(f"平均耗时\n{stats['avg_duration_ms']} ms")
        self.metric_risk_count_card.setText(f"风控次数\n{stats['risk_count']}")
        self.metric_total_traffic_card.setText(
            f"总流量\n↑ {self._format_human_bytes(stats['total_upload_bytes'])} / ↓ {self._format_human_bytes(stats['total_download_bytes'])}"
        )
        self.metric_avg_traffic_card.setText(
            f"平均流量\n↑ {self._format_human_bytes(stats['avg_upload_bytes'])} / ↓ {self._format_human_bytes(stats['avg_download_bytes'])}"
        )
        self.metric_blocked_card.setText(f"资源拦截\n{stats['total_blocked']} / {stats['avg_blocked']}")
        distribution = stats["error_distribution"]
        if distribution:
            lines = [f"{code}: {count}" for code, count in distribution.items()]
            self.error_distribution_view.setPlainText("\n".join(lines))
        else:
            self.error_distribution_view.setPlainText("最近 100 个任务暂无错误记录")

    def _refresh_result_files(self) -> None:
        for path in self.result_views:
            self._refresh_single_result_file(path)
        self._refresh_risk_status()
        self._refresh_task_table()
        self._refresh_dashboard_stats()

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

    def _test_proxy_health(self) -> None:
        config = self._build_config_from_form()
        try:
            config.validate()
        except ConfigValidationError as exc:
            QMessageBox.warning(self, "配置校验失败", "\n".join(exc.errors))
            return

        proxy_manager = ProxyManager(
            static_proxy=config.proxy.url,
            dynamic_proxy_config=config.oauth2.dynamic_residential_proxy,
        )
        result = proxy_manager.check_health()

        lines = [
            f"连通状态: {'正常' if result['connect_ok'] else '失败'}",
            f"认证状态: {'已识别' if result['auth_ok'] else '未识别'}",
            f"出口 IP: {result['ip'] or '-'}",
            f"出口国家: {result['country'] or '-'}",
            f"国家匹配: {result['country_match'] if result['country_match'] is not None else '未配置'}",
            f"粘性会话: {result['sticky_session'] if result['sticky_session'] is not None else '未配置'}",
            f"消息: {result['message']}",
        ]
        QMessageBox.information(self, "代理健康检查", "\n".join(lines))
        self.status_label.setText(f"代理检测完成: {result['message']}")

    def _prepare_tasks(self) -> None:
        if not self._save_form_to_config(show_popup=False):
            return

        config = AppConfig.load()
        db = TaskDB()
        db.clear_all_tasks()
        for _ in range(config.max_tasks):
            db.create_task(random_email(), generate_strong_password())

        QMessageBox.information(self, "准备完成", f"任务库已重建，共生成 {config.max_tasks} 条任务")
        self.status_label.setText(f"已初始化任务库，共 {config.max_tasks} 条")
        self.metric_tasks_card.setText(f"任务池\n待执行 {config.max_tasks} / 运行中 0")
        self._refresh_result_files()
        logger.info("Task database reinitialized from GUI")

    def _create_task_callable(self):
        def task(is_cancelled) -> None:
            config = AppConfig.load()
            db = TaskDB()
            db.reset_in_progress_tasks()
            controller = build_controller(config)
            context = RuntimeContext(config=config, result_store=ResultStore())
            runner = FlowRunner(controller=controller, context=context)
            circuit_breaker = RiskCircuitBreaker(
                max_consecutive_risk=config.risk_control.max_consecutive_risk,
                max_failure_streak=config.risk_control.max_failure_streak,
            )

            pending_tasks = db.get_pending_tasks(limit=config.max_tasks)
            if not pending_tasks:
                for _ in range(config.max_tasks):
                    db.create_task(random_email(), generate_strong_password())
                pending_tasks = db.get_pending_tasks(limit=config.max_tasks)

            success_count = 0
            failed_count = 0

            from threading import Lock
            counter_lock = Lock()

            def process_task(task_item) -> FlowResult:
                nonlocal success_count, failed_count
                task_id, email, password, retry_mode = task_item

                if is_cancelled() or circuit_breaker.should_stop():
                    logger.info("任务已被手动停止或风险熔断终止")
                    db.update_task_status(
                        task_id,
                        "pending",
                        circuit_breaker.stop_reason() or "Cancelled before execution",
                        error_code=ErrorCode.RISK_STOPPED.value if circuit_breaker.should_stop() else "",
                        stage=Stage.INIT.value,
                        risk_detected=circuit_breaker.should_stop(),
                    )
                    return FlowResult.fail(
                        ErrorCode.RISK_STOPPED,
                        circuit_breaker.stop_reason() or "Cancelled before execution",
                        Stage.INIT,
                        risk_detected=circuit_breaker.should_stop(),
                    )

                db.update_task_status(task_id, "in_progress", stage=Stage.INIT.value)
                result = runner.process_single_flow_with_credentials(
                    task_id=task_id,
                    email=email,
                    password=password,
                    retry_mode=retry_mode,
                )
                if result.success:
                    db.update_task_status(task_id, "success", stage=result.stage)
                    with counter_lock:
                        success_count += 1
                    return result

                db.update_task_status(
                    task_id,
                    "failed",
                    result.error_message,
                    error_code=result.error_code,
                    stage=result.stage,
                    risk_detected=result.risk_detected,
                )
                with counter_lock:
                    failed_count += 1
                return result

            try:
                from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

                task_iter = iter(pending_tasks)
                max_workers = max(1, config.concurrent_flows)
                if config.choose_browser == "patchright":
                    max_workers = 1
                    logger.warning("Patchright 同步模式已强制限制为单线程，避免跨线程 greenlet 错误")
                submitted_count = 0

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {}

                    while not is_cancelled() and not circuit_breaker.should_stop() and len(future_map) < max_workers:
                        try:
                            task_item = next(task_iter)
                        except StopIteration:
                            break
                        future = executor.submit(process_task, task_item)
                        future_map[future] = task_item
                        submitted_count += 1

                    while future_map:
                        done_futures, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED)
                        for future in done_futures:
                            task_item = future_map.pop(future)
                            try:
                                result = future.result()
                                circuit_breaker.record_result(result)
                                if circuit_breaker.should_stop():
                                    logger.warning("GUI risk circuit breaker triggered: %s", circuit_breaker.stop_reason())
                            except Exception as exc:
                                task_id, _, _ = task_item
                                result = FlowResult.fail(ErrorCode.UNKNOWN_ERROR, str(exc), Stage.INIT)
                                db.update_task_status(
                                    task_id,
                                    "failed",
                                    str(exc),
                                    error_code=result.error_code,
                                    stage=result.stage,
                                )
                                circuit_breaker.record_result(result)
                                with counter_lock:
                                    failed_count += 1
                                logger.exception("GUI task %s failed: %s", task_id, exc)

                            while not is_cancelled() and not circuit_breaker.should_stop() and len(future_map) < max_workers:
                                try:
                                    next_task = next(task_iter)
                                except StopIteration:
                                    break
                                next_future = executor.submit(process_task, next_task)
                                future_map[next_future] = next_task
                                submitted_count += 1

                        if is_cancelled() or circuit_breaker.should_stop():
                            break

                if circuit_breaker.should_stop():
                    logger.warning("检测到风险，任务已自动中止: %s", circuit_breaker.stop_reason())
                    self.risk_status_label.setText(f"风险状态：已熔断 - {circuit_breaker.stop_reason()}")
                    self.metric_risk_card.setText("风险监控\n已熔断")
                elif is_cancelled():
                    logger.info("任务已被用户手动停止")
                    self.risk_status_label.setText("风险状态：用户已停止")
                    self.metric_status_card.setText("运行状态\n已中止")

                print(f"\n[Result] - 共: {submitted_count}, 成功 {success_count}, 失败 {failed_count}")
            finally:
                controller.clean_up(type="all_browser")

        return task

    def _start_task(self, show_popup: bool = False) -> None:
        if self.task_controller is not None:
            QMessageBox.information(self, "提示", "已有任务正在执行")
            return

        if not self._save_form_to_config(show_popup=show_popup):
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.task_controller = TaskThreadController(self._create_task_callable())
        self.task_controller.log_message.connect(self._append_log)
        self.task_controller.task_finished.connect(self._handle_task_finished)
        self.task_controller.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("任务已启动")
        self.metric_status_card.setText("运行状态\n执行中")
        self.metric_risk_card.setText("风险监控\n监控中")
        self.tabs.setCurrentWidget(self.console_tab)

    def _stop_task(self) -> None:
        if self.task_controller is not None:
            self.status_label.setText("正在停止任务，请等待当前操作完成...")
            self.metric_status_card.setText("运行状态\n停止中")
            self.stop_button.setEnabled(False)
            self.task_controller.stop()

    def _handle_task_finished(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        self.metric_status_card.setText(f"运行状态\n{'已完成' if success else '已停止'}")
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "停止/失败", message)

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.task_controller = None
        self._refresh_result_files()
        self._load_log_file()


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
