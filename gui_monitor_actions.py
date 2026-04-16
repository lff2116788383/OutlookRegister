from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QFileDialog, QMessageBox

from account_io import load_email_accounts
from app_config import PENDING_OAUTH_ACCOUNTS_PATH

from app_config import APP_LOG_PATH
from database import TaskDB
from result_store import ResultStore


def choose_log_file(window) -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        window,
        "选择日志文件",
        str(APP_LOG_PATH.parent),
        "Log Files (*.log *.txt);;All Files (*)",
    )
    if file_path:
        window.log_path = Path(file_path)
        window._load_log_file()



def highlight_log_line(window, text: str) -> None:
    cursor = window.log_output.textCursor()
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
    window.log_output.setTextCursor(cursor)
    window.log_output.ensureCursorVisible()



def append_log(window, text: str) -> None:
    window._highlight_log_line(text)
    with window.log_path.open("a", encoding="utf-8") as file:
        file.write(text)



def load_log_file(window) -> None:
    if not window.log_path.exists():
        window.log_output.setPlainText("")
        return
    window.log_output.setPlainText("")
    for line in window.log_path.read_text(encoding="utf-8").splitlines(True):
        window._highlight_log_line(line)



def clear_log_file(window) -> None:
    if window.log_path.exists():
        window.log_path.write_text("", encoding="utf-8")
    window.log_output.clear()
    window.status_label.setText(f"已清空日志: {window.log_path.name}")



def format_human_bytes(window, size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(max(0, size))
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} GB"



def refresh_dashboard_stats(window) -> None:
    stats = ResultStore().get_dashboard_stats(recent_limit=100)
    summary_text = (
        f"成功数: {stats.get('register_success', 0)} | "
        f"失败数: {stats.get('register_failed', 0)} | "
        f"注册成功率: {stats['register_success_rate']}% | "
        f"平均耗时: {stats['avg_duration_ms']} ms | "
        f"总流量: ↑ {window._format_human_bytes(stats['total_upload_bytes'])} / ↓ {window._format_human_bytes(stats['total_download_bytes'])} | "
        f"平均流量: ↑ {window._format_human_bytes(stats['avg_upload_bytes'])} / ↓ {window._format_human_bytes(stats['avg_download_bytes'])}"
    )
    if hasattr(window, "register_stats_summary_label"):
        window.register_stats_summary_label.setText(summary_text)
        return

    window.metric_register_rate_card.setText(f"注册成功率\n{stats['register_success_rate']}%")
    window.metric_avg_duration_card.setText(f"平均耗时\n{stats['avg_duration_ms']} ms")
    if hasattr(window, "metric_risk_count_card"):
        window.metric_risk_count_card.setText(f"风控次数\n{stats['risk_count']}")
    window.metric_total_traffic_card.setText(
        f"总流量\n↑ {window._format_human_bytes(stats['total_upload_bytes'])} / ↓ {window._format_human_bytes(stats['total_download_bytes'])}"
    )
    window.metric_avg_traffic_card.setText(
        f"平均流量\n↑ {window._format_human_bytes(stats['avg_upload_bytes'])} / ↓ {window._format_human_bytes(stats['avg_download_bytes'])}"
    )
    if hasattr(window, "metric_blocked_card"):
        window.metric_blocked_card.setText(f"资源拦截\n{stats['total_blocked']} / {stats['avg_blocked']}")
    if hasattr(window, "error_distribution_view"):
        distribution = stats["error_distribution"]
        if distribution:
            lines = [f"{code}: {count}" for code, count in distribution.items()]
            window.error_distribution_view.setPlainText("\n".join(lines))
        else:
            window.error_distribution_view.setPlainText("最近 100 个任务暂无错误记录")



def refresh_result_files(window) -> None:
    for path in window.result_views:
        window._refresh_single_result_file(path)
    if hasattr(window, "register_stats_summary_label") or hasattr(window, "metric_register_rate_card"):
        window._refresh_dashboard_stats()



def refresh_single_result_file(window, path: Path) -> None:
    viewer = window.result_views[path]
    if path.exists():
        viewer.setPlainText(path.read_text(encoding="utf-8"))
    else:
        viewer.setPlainText("")



def clear_single_result_file(window, path: Path) -> None:
    reply = QMessageBox.question(
        window,
        "确认清空",
        f"确认清空结果文件：{path.name} ?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    window._refresh_single_result_file(path)
    window.status_label.setText(f"已清空结果文件: {path.name}")



def export_registered_results(window) -> None:
    source_path = PENDING_OAUTH_ACCOUNTS_PATH
    accounts = load_email_accounts(source_path)
    if not accounts:
        QMessageBox.information(window, "提示", "当前没有可导出的注册结果")
        return

    file_path, selected_filter = QFileDialog.getSaveFileName(
        window,
        "导出注册结果",
        str(source_path),
        "Text Files (*.txt);;JSON Files (*.json);;CSV Files (*.csv)",
    )
    if not file_path:
        return

    target_path = Path(file_path)
    suffix = target_path.suffix.lower()
    if not suffix:
        if "*.json" in selected_filter:
            target_path = target_path.with_suffix(".json")
            suffix = ".json"
        elif "*.csv" in selected_filter:
            target_path = target_path.with_suffix(".csv")
            suffix = ".csv"
        else:
            target_path = target_path.with_suffix(".txt")
            suffix = ".txt"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".json":
        payload = [{"email": item.email, "password": item.password} for item in accounts]
        target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    elif suffix == ".csv":
        with target_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["email", "password"])
            for item in accounts:
                writer.writerow([item.email, item.password])
    else:
        target_path.write_text(
            "\n".join(f"{item.email}----{item.password}" for item in accounts) + "\n",
            encoding="utf-8",
        )

    window.status_label.setText(f"已导出 {len(accounts)} 个注册结果: {target_path.name}")
    QMessageBox.information(window, "导出完成", f"已导出到:\n{target_path}")



def clear_all_result_files(window) -> None:
    reply = QMessageBox.question(
        window,
        "确认清空",
        "确认清空全部结果文件吗？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    for path in window.result_views:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    window._refresh_result_files()
    window.status_label.setText("已清空全部结果文件")
