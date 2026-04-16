from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from account_io import export_token_accounts, load_email_accounts
from app_config import OAUTH_TOKEN_ACCOUNTS_PATH
from gui_runner import TaskThreadController
from logger import logger
from mam_client import build_microsoft_account_manager_client
from oauth_account_runner import run_oauth_accounts


def choose_oauth_import_file(window) -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        window,
        "选择待 OAuth2 的邮箱账号文件",
        str(Path("Results")),
        "Text Files (*.txt);;All Files (*)",
    )
    if file_path:
        window.oauth_import_path = Path(file_path)
        window.oauth_import_path_input.setText(file_path)
        window._refresh_oauth_account_summary()



def load_oauth_accounts_from_file(window) -> None:
    raw_path = window.oauth_import_path_input.text().strip()
    if raw_path:
        window.oauth_import_path = Path(raw_path)
    if not window.oauth_import_path:
        QMessageBox.information(window, "提示", "请先选择账号文件")
        return
    if not window.oauth_import_path.exists():
        QMessageBox.warning(window, "导入失败", f"文件不存在:\n{window.oauth_import_path}")
        return

    try:
        window.oauth_loaded_accounts = load_email_accounts(window.oauth_import_path)
    except Exception as exc:
        QMessageBox.critical(window, "导入失败", f"读取账号文件失败:\n{exc}")
        return

    window.oauth_success_accounts = []
    window.oauth_last_results = []
    window.oauth_last_upload_status = "未上传"
    window._refresh_oauth_account_summary()
    if hasattr(window, "status_label") and window.status_label is not None:
        try:
            if window.oauth_loaded_accounts:
                window.status_label.setText(f"已导入 {len(window.oauth_loaded_accounts)} 个待 OAuth2 邮箱账号")
            else:
                window.status_label.setText("导入完成，但文件中没有有效账号")
        except RuntimeError:
            pass

    if not window.oauth_loaded_accounts:
        QMessageBox.information(window, "导入结果", f"文件中没有可用账号:\n{window.oauth_import_path}")
        return



def refresh_oauth_account_summary(window) -> None:
    import_path = str(window.oauth_import_path) if window.oauth_import_path else "未选择"
    loaded_count = len(getattr(window, "oauth_loaded_accounts", []))
    success_count = len(getattr(window, "oauth_success_accounts", []))
    result_count = len(getattr(window, "oauth_last_results", []))
    failed_count = max(0, result_count - success_count)
    success_rate = round((success_count / result_count) * 100, 2) if result_count else 0
    failure_distribution = {}
    for item in getattr(window, "oauth_last_results", []):
        if item.success:
            continue
        error_code = str(item.error_code or "UNKNOWN")
        failure_distribution[error_code] = failure_distribution.get(error_code, 0) + 1
    sorted_failures = sorted(failure_distribution.items(), key=lambda entry: (-entry[1], entry[0]))
    failure_summary = "无"
    failure_detail_text = "暂无失败原因"
    if sorted_failures:
        failure_summary = ", ".join(f"{code}:{count}" for code, count in sorted_failures[:5])
        failure_detail_text = "\n".join(f"{code}: {count}" for code, count in sorted_failures)
    upload_status = getattr(window, "oauth_last_upload_status", "未上传")
    if loaded_count:
        preview_lines = [
            item.email
            for item in getattr(window, "oauth_loaded_accounts", [])[:10]
        ]
        if loaded_count > 10:
            preview_lines.append(f"... 其余 {loaded_count - 10} 个未展开")
        preview_text = "\n".join(preview_lines)
    else:
        preview_text = "当前文件中没有解析到有效账号"

    window.oauth_loaded_summary_label.setText(
        f"文件: {import_path}\n已导入: {loaded_count} 个"
    )
    if hasattr(window, "oauth_loaded_accounts_view"):
        window.oauth_loaded_accounts_view.setPlainText(preview_text)

    if hasattr(window, "oauth_stats_summary_label"):
        window.oauth_stats_summary_label.setText(
            f"导入数: {loaded_count} | 执行数: {result_count} | 成功数: {success_count} | "
            f"失败数: {failed_count} | 成功率: {success_rate}% | 上传状态: {upload_status} | 失败原因: {failure_summary}"
        )
    if hasattr(window, "oauth_failure_reason_view"):
        window.oauth_failure_reason_view.setPlainText(failure_detail_text)

    if result_count:
        lines = []
        for item in window.oauth_last_results:
            if item.success:
                lines.append(f"成功: {item.email}")
            else:
                detail = (item.error_message or "").strip()
                if detail:
                    lines.append(f"失败: {item.email} | {item.error_code or 'UNKNOWN'}\n{detail}")
                else:
                    lines.append(f"失败: {item.email} | {item.error_code or 'UNKNOWN'}")
        window.oauth_result_summary_view.setPlainText("\n\n".join(lines))
    else:
        if success_count:
            window.oauth_result_summary_view.setPlainText(
                f"已生成 Token 账号 {success_count} 个，可导出或上传到 MAM。"
            )
        else:
            window.oauth_result_summary_view.setPlainText("尚未执行 OAuth2，或当前没有可导出的 Token 账号")

    window.oauth_export_button.setEnabled(success_count > 0)
    if hasattr(window, "oauth_upload_button"):
        window.oauth_upload_button.setEnabled(success_count > 0)



def create_oauth_task_callable(window):
    def task(is_cancelled) -> None:
        if is_cancelled():
            return
        results = run_oauth_accounts(window.oauth_loaded_accounts)
        if is_cancelled():
            return
        window.oauth_last_results = results
        window.oauth_success_accounts = [item.token_account for item in results if item.success and item.token_account is not None]
        export_token_accounts(OAUTH_TOKEN_ACCOUNTS_PATH, window.oauth_success_accounts)
        logger.info(
            "GUI OAuth task finished. loaded=%s success=%s failed=%s",
            len(window.oauth_loaded_accounts),
            len(window.oauth_success_accounts),
            len(results) - len(window.oauth_success_accounts),
        )

        config = window._build_config_from_form()
        window.oauth_last_upload_status = "未启用自动上传"
        if window.oauth_success_accounts and config.microsoft_account_manager.enabled and config.microsoft_account_manager.upload_after_oauth:
            client = build_microsoft_account_manager_client(config)
            upload_result = client.upload_token_accounts(window.oauth_success_accounts)
            if upload_result.ok:
                window.oauth_last_upload_status = f"自动上传成功({len(window.oauth_success_accounts)})"
                logger.info("OAuth GUI auto upload succeeded: %s", upload_result.message)
            else:
                window.oauth_last_upload_status = f"自动上传失败: {upload_result.message}"
                logger.warning("OAuth GUI auto upload failed: %s", upload_result.message)

    return task



def run_oauth_accounts_gui(window) -> None:
    if getattr(window, "oauth_task_controller", None) is not None:
        QMessageBox.information(window, "提示", "已有 OAuth2 任务正在执行")
        return
    if window.task_controller is not None:
        QMessageBox.information(window, "提示", "当前注册任务正在执行，请稍后再运行 OAuth2")
        return
    if not getattr(window, "oauth_loaded_accounts", []):
        QMessageBox.information(window, "提示", "请先导入待 OAuth2 账号")
        return

    try:
        config = window._build_config_from_form()
        config.validate()
    except Exception as exc:
        QMessageBox.warning(window, "配置校验失败", str(exc))
        return

    window.status_label.setText("OAuth2 任务已启动")
    if hasattr(window, "metric_status_card"):
        window.metric_status_card.setText("运行状态\nOAuth2 中")
    window.oauth_run_button.setEnabled(False)
    window.oauth_export_button.setEnabled(False)
    if hasattr(window, "oauth_upload_button"):
        window.oauth_upload_button.setEnabled(False)
    window.oauth_task_controller = TaskThreadController(window._create_oauth_task_callable())
    window.oauth_task_controller.log_message.connect(window._append_log)
    window.oauth_task_controller.task_finished.connect(window._handle_oauth_task_finished)
    window.oauth_task_controller.start()



def export_oauth_success_accounts(window) -> None:
    accounts = getattr(window, "oauth_success_accounts", [])
    if not accounts:
        QMessageBox.information(window, "提示", "当前没有可导出的 Token 账号")
        return

    file_path, _ = QFileDialog.getSaveFileName(
        window,
        "导出 OAuth2 Token 账号",
        str(OAUTH_TOKEN_ACCOUNTS_PATH),
        "Text Files (*.txt)",
    )
    if not file_path:
        return

    export_token_accounts(Path(file_path), accounts)
    window.status_label.setText(f"已导出 {len(accounts)} 个 Token 账号")
    QMessageBox.information(window, "导出完成", f"已导出到:\n{file_path}")



def upload_oauth_success_accounts(window) -> None:
    accounts = getattr(window, "oauth_success_accounts", [])
    if not accounts:
        QMessageBox.information(window, "提示", "当前没有可上传的 Token 账号")
        return

    try:
        config = window._build_config_from_form()
        config.validate()
    except Exception as exc:
        QMessageBox.warning(window, "配置校验失败", str(exc))
        return

    client = build_microsoft_account_manager_client(config)
    result = client.upload_token_accounts(accounts)
    if result.ok:
        window.oauth_last_upload_status = f"手动上传成功({len(accounts)})"
        window._refresh_oauth_account_summary()
        window.status_label.setText(f"上传成功: {result.message}")
        QMessageBox.information(window, "上传成功", result.message)
    else:
        window.oauth_last_upload_status = f"手动上传失败: {result.message}"
        window._refresh_oauth_account_summary()
        window.status_label.setText(f"上传失败: {result.message}")
        QMessageBox.warning(window, "上传失败", result.message)



def handle_oauth_task_finished(window, success: bool, message: str) -> None:
    window.oauth_task_controller = None
    window.oauth_run_button.setEnabled(True)
    window._refresh_oauth_account_summary()
    window._refresh_result_files()
    if hasattr(window, "metric_status_card"):
        window.metric_status_card.setText(f"运行状态\n{'已完成' if success else '已停止'}")
    if success:
        success_count = len(getattr(window, "oauth_success_accounts", []))
        total_count = len(getattr(window, "oauth_last_results", []))
        window.status_label.setText(f"OAuth2 完成：成功 {success_count} / 总计 {total_count}")
        QMessageBox.information(window, "OAuth2 完成", f"成功 {success_count} / 总计 {total_count}")
    else:
        window.status_label.setText(message)
        QMessageBox.warning(window, "OAuth2 停止/失败", message)
