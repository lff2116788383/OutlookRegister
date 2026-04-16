from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_state import RESULT_FILES



def build_console_tab(
    window,
    target_tab=None,
    *,
    include_register_section: bool = True,
    include_oauth_section: bool = True,
) -> None:
    tab = target_tab or getattr(window, "console_tab", None) or getattr(window, "register_tab")
    outer_layout = QVBoxLayout(tab)
    outer_layout.setContentsMargins(10, 10, 10, 10)
    outer_layout.setSpacing(0)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    content = QWidget()
    root_layout = QVBoxLayout(content)
    root_layout.setContentsMargins(8, 8, 8, 8)
    root_layout.setSpacing(12)

    if include_register_section:
        window.result_views = {}

    is_register_only = include_register_section and not include_oauth_section
    hero_group = QGroupBox("注册邮箱账号" if is_register_only else "邮箱账号 OAuth2")
    hero_layout = QVBoxLayout(hero_group)
    hero_layout.setSpacing(8)
    hero_title = QLabel("Register Accounts" if is_register_only else "Existing Account OAuth2")
    hero_title.setProperty("role", "heroTitle")
    hero_subtitle = QLabel(
        "注册 Tab 只负责多线程批量注册邮箱账号，并输出注册成功邮箱账号。"
        if is_register_only
        else "OAuth2 Tab 负责导入已有邮箱账号、执行登录检测与 OAuth2、导出 token 并上传到 MAM。"
    )
    hero_subtitle.setProperty("role", "heroSubtitle")
    hero_layout.addWidget(hero_title)
    hero_layout.addWidget(hero_subtitle)

    console_panel = QWidget()
    console_layout = QVBoxLayout(console_panel)
    console_layout.setContentsMargins(0, 0, 0, 0)
    console_layout.setSpacing(12)

    if include_register_section:
        control_group = QGroupBox("批量注册")
        control_layout = QGridLayout(control_group)
        control_layout.setHorizontalSpacing(10)
        control_layout.setVerticalSpacing(10)
        control_hint = QLabel("设置任务数、并发数和邮箱后缀后直接启动批量注册。其它代理、验证码、浏览器等高级参数仍在配置页维护。")
        control_hint.setProperty("role", "sectionHint")
        control_hint.setWordWrap(True)
        window.status_label = QLabel("就绪")
        window.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        window.status_label.setProperty("role", "statusPanel")

        window.register_max_tasks_input = QSpinBox()
        window.register_max_tasks_input.setRange(1, 100000)
        window.register_concurrent_input = QSpinBox()
        window.register_concurrent_input.setRange(1, 100)
        window.register_email_domain_combo = QComboBox()
        window.register_email_domain_combo.addItems(["outlook.com", "hotmail.com"])
        window.register_email_domain_combo.setCurrentText("outlook.com")
        window.start_button = QPushButton("开始批量注册")
        window.stop_button = QPushButton("停止")
        window.stop_button.setEnabled(False)
        window.log_output = QPlainTextEdit()
        window.log_output.setReadOnly(True)
        window.log_output.hide()

        register_stats_group = QGroupBox("注册统计")
        register_stats_layout = QVBoxLayout(register_stats_group)
        register_stats_layout.setSpacing(8)
        register_stats_hint = QLabel("只保留批量注册过程中最常用的统计摘要。")
        register_stats_hint.setProperty("role", "sectionHint")
        register_stats_hint.setWordWrap(True)
        window.register_stats_summary_label = QLabel(
            "成功数: 0 | 失败数: 0 | 注册成功率: 0% | 平均耗时: 0 ms | 总流量: 0 B / 0 B | 平均流量: 0 B / 0 B"
        )
        window.register_stats_summary_label.setWordWrap(True)
        window.register_stats_summary_label.setProperty("role", "statusPanel")
        register_stats_layout.addWidget(register_stats_hint)
        register_stats_layout.addWidget(window.register_stats_summary_label)

        control_layout.addWidget(control_hint, 0, 0, 1, 8)
        control_layout.addWidget(QLabel("任务数"), 1, 0)
        control_layout.addWidget(window.register_max_tasks_input, 1, 1)
        control_layout.addWidget(QLabel("并发数"), 1, 2)
        control_layout.addWidget(window.register_concurrent_input, 1, 3)
        control_layout.addWidget(QLabel("邮箱后缀"), 1, 4)
        control_layout.addWidget(window.register_email_domain_combo, 1, 5)
        control_layout.addWidget(window.start_button, 1, 6)
        control_layout.addWidget(window.stop_button, 1, 7)
        control_layout.addWidget(window.status_label, 2, 0, 1, 8)
        control_layout.setColumnStretch(5, 1)

        results_group = QGroupBox("注册结果")
        results_layout = QVBoxLayout(results_group)
        results_layout.setSpacing(10)

        result_header_layout = QHBoxLayout()
        result_header_hint = QLabel("注册页结果区仅展示注册成功邮箱账号，避免与 OAuth2 结果混在一起。")
        result_header_hint.setProperty("role", "sectionHint")
        result_header_layout.addWidget(result_header_hint)
        result_header_layout.addStretch(1)
        results_layout.addLayout(result_header_layout)

        register_result_group = QGroupBox("注册成功邮箱账号")
        register_result_layout = QVBoxLayout(register_result_group)
        register_result_layout.setSpacing(8)

        register_result_action_layout = QHBoxLayout()
        register_refresh_button = QPushButton("刷新")
        register_export_button = QPushButton("导出")
        register_clear_button = QPushButton("清空")
        register_result_action_layout.addWidget(register_refresh_button)
        register_result_action_layout.addWidget(register_export_button)
        register_result_action_layout.addWidget(register_clear_button)
        register_result_action_layout.addStretch(1)

        register_result_viewer = QPlainTextEdit()
        register_result_viewer.setReadOnly(True)
        register_result_viewer.setPlaceholderText("注册成功邮箱账号 暂无内容")
        register_result_viewer.setMinimumHeight(180)

        register_result_layout.addLayout(register_result_action_layout)
        register_result_layout.addWidget(register_result_viewer)
        window.result_views[RESULT_FILES[0].path] = register_result_viewer

        register_refresh_button.clicked.connect(
            lambda _checked=False, path=RESULT_FILES[0].path: window._refresh_single_result_file(path)
        )
        register_export_button.clicked.connect(window._export_registered_results)
        register_clear_button.clicked.connect(
            lambda _checked=False, path=RESULT_FILES[0].path: window._clear_single_result_file(path)
        )

        results_layout.addWidget(register_result_group)

        console_layout.addWidget(control_group)
        console_layout.addWidget(results_group)
        console_layout.addWidget(register_stats_group)

    if include_oauth_section:
        oauth_group = QGroupBox("已有邮箱账号 OAuth2")
        oauth_layout = QVBoxLayout(oauth_group)
        oauth_layout.setSpacing(10)
        oauth_hint = QLabel("OAuth2 页建议拆成两块：上面管理导入邮箱账号，下面管理导出/上传 token 账号。")
        oauth_hint.setProperty("role", "sectionHint")
        oauth_hint.setWordWrap(True)

        oauth_import_group = QGroupBox("导入邮箱账号")
        oauth_import_layout = QVBoxLayout(oauth_import_group)
        oauth_import_layout.setSpacing(10)
        oauth_import_hint = QLabel("导入 email----password 账号列表，执行旧号登录检测与 OAuth2。")
        oauth_import_hint.setProperty("role", "sectionHint")
        oauth_import_hint.setWordWrap(True)

        oauth_file_layout = QGridLayout()
        oauth_file_layout.setHorizontalSpacing(10)
        oauth_file_layout.setVerticalSpacing(8)
        oauth_file_label = QLabel("账号文件")
        oauth_file_label.setProperty("role", "sectionHint")
        window.oauth_import_path_input = QLineEdit()
        window.oauth_import_path_input.setPlaceholderText("选择待 OAuth2 的邮箱账号 txt 文件")
        window.oauth_choose_file_button = QPushButton("选择账号文件")
        window.oauth_choose_file_button.setToolTip("只选择待 OAuth2 的 email----password txt 文件，不读取内容")
        window.oauth_load_accounts_button = QPushButton("读取账号")
        window.oauth_load_accounts_button.setToolTip("读取左侧文件内容，并把有效邮箱账号加载到下方预览框")
        oauth_file_layout.addWidget(oauth_file_label, 0, 0)
        oauth_file_layout.addWidget(window.oauth_import_path_input, 0, 1)
        oauth_file_layout.addWidget(window.oauth_choose_file_button, 0, 2)
        oauth_file_layout.addWidget(window.oauth_load_accounts_button, 0, 3)
        oauth_file_layout.setColumnStretch(1, 1)

        window.oauth_loaded_summary_label = QLabel("未导入账号")
        window.oauth_loaded_summary_label.setProperty("role", "statusPanel")
        window.oauth_loaded_accounts_view = QPlainTextEdit()
        window.oauth_loaded_accounts_view.setReadOnly(True)
        window.oauth_loaded_accounts_view.setPlaceholderText("导入后的邮箱账号预览将在此显示…")
        window.oauth_loaded_accounts_view.setMinimumHeight(140)
        window.oauth_loaded_accounts_view.setMaximumHeight(220)

        oauth_import_layout.addWidget(oauth_import_hint)
        oauth_import_layout.addLayout(oauth_file_layout)
        oauth_import_layout.addWidget(QLabel("导入结果"))
        oauth_import_layout.addWidget(window.oauth_loaded_summary_label)
        oauth_import_layout.addWidget(QLabel("已导入邮箱账号预览"))
        oauth_import_layout.addWidget(window.oauth_loaded_accounts_view)

        oauth_token_group = QGroupBox("导出 / 上传 Token 账号")
        oauth_token_layout = QVBoxLayout(oauth_token_group)
        oauth_token_layout.setSpacing(10)
        oauth_token_hint = QLabel("OAuth2 成功后，这里展示 token 账号结果，并支持导出与上传到 MAM。")
        oauth_token_hint.setProperty("role", "sectionHint")
        oauth_token_hint.setWordWrap(True)

        oauth_action_layout = QGridLayout()
        oauth_action_layout.setHorizontalSpacing(10)
        oauth_action_layout.setVerticalSpacing(8)
        oauth_action_label = QLabel("Token 操作")
        oauth_action_label.setProperty("role", "sectionHint")
        window.oauth_run_button = QPushButton("执行 OAuth2")
        window.oauth_export_button = QPushButton("导出 Token")
        window.oauth_export_button.setEnabled(False)
        window.oauth_upload_button = QPushButton("上传到 MAM")
        window.oauth_upload_button.setEnabled(False)
        oauth_action_layout.addWidget(oauth_action_label, 0, 0)
        oauth_action_layout.addWidget(window.oauth_run_button, 0, 1)
        oauth_action_layout.addWidget(window.oauth_export_button, 0, 2)
        oauth_action_layout.addWidget(window.oauth_upload_button, 0, 3)
        oauth_action_layout.setColumnStretch(4, 1)

        window.oauth_stats_summary_label = QLabel(
            "导入数: 0 | 执行数: 0 | 成功数: 0 | 失败数: 0 | 成功率: 0% | 上传状态: 未上传 | 失败原因: 无"
        )
        window.oauth_stats_summary_label.setWordWrap(True)
        window.oauth_stats_summary_label.setProperty("role", "statusPanel")
        window.oauth_failure_reason_view = QPlainTextEdit()
        window.oauth_failure_reason_view.setReadOnly(True)
        window.oauth_failure_reason_view.setPlaceholderText("OAuth2 失败原因聚合将在此显示…")
        window.oauth_failure_reason_view.setMinimumHeight(90)
        window.oauth_failure_reason_view.setMaximumHeight(150)
        window.oauth_result_summary_view = QPlainTextEdit()
        window.oauth_result_summary_view.setReadOnly(True)
        window.oauth_result_summary_view.setPlaceholderText("OAuth2 执行结果与 token 账号摘要将在此显示…")
        window.oauth_result_summary_view.setMinimumHeight(220)

        oauth_token_layout.addWidget(oauth_token_hint)
        oauth_token_layout.addLayout(oauth_action_layout)
        oauth_token_layout.addWidget(QLabel("OAuth2 统计"))
        oauth_token_layout.addWidget(window.oauth_stats_summary_label)
        oauth_token_layout.addWidget(QLabel("失败原因聚合"))
        oauth_token_layout.addWidget(window.oauth_failure_reason_view)
        oauth_token_layout.addWidget(QLabel("Token 结果 / 摘要"))
        oauth_token_layout.addWidget(window.oauth_result_summary_view)

        oauth_layout.addWidget(oauth_hint)
        oauth_layout.addWidget(oauth_import_group)
        oauth_layout.addWidget(oauth_token_group)

        console_layout.addWidget(oauth_group)

    console_layout.addStretch(1)

    root_layout.addWidget(hero_group)
    root_layout.addWidget(console_panel)

    scroll_area.setWidget(content)
    outer_layout.addWidget(scroll_area)

    if include_register_section:
        window.start_button.clicked.connect(window._start_task)
        window.stop_button.clicked.connect(window._stop_task)

    if include_oauth_section:
        window.oauth_choose_file_button.clicked.connect(window._choose_oauth_import_file)
        window.oauth_load_accounts_button.clicked.connect(window._load_oauth_accounts_from_file)
        window.oauth_run_button.clicked.connect(window._run_oauth_accounts)
        window.oauth_export_button.clicked.connect(window._export_oauth_success_accounts)
        window.oauth_upload_button.clicked.connect(window._upload_oauth_success_accounts)



def status_color(status: str) -> QColor:
    return {
        "success": QColor("#22c55e"),
        "failed": QColor("#ef4444"),
        "in_progress": QColor("#38bdf8"),
        "pending": QColor("#94a3b8"),
        "reserved": QColor("#f59e0b"),
    }.get(status, QColor("#e2e8f0"))
