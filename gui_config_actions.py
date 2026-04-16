from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app_config import AppConfig, CONFIG_PATH, ConfigValidationError


def choose_config_file(window) -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        window,
        "选择配置文件",
        str(CONFIG_PATH.parent),
        "JSON Files (*.json)",
    )
    if file_path:
        window._load_config_to_form(Path(file_path))



def load_config_to_form(window, config_path: Path | None = None, show_popup: bool = True) -> None:
    resolved_config_path = Path(config_path or CONFIG_PATH)
    config = AppConfig.load(resolved_config_path)
    window.loaded_config_path = resolved_config_path

    window.browser_combo.setCurrentText(config.choose_browser)
    window.email_domain_combo.setCurrentText(config.email_domain)
    if hasattr(window, "register_email_domain_combo"):
        window.register_email_domain_combo.setCurrentText(config.email_domain)
    if hasattr(window, "register_concurrent_input"):
        window.register_concurrent_input.setValue(config.concurrent_flows)
    if hasattr(window, "register_max_tasks_input"):
        window.register_max_tasks_input.setValue(config.max_tasks)
    window.proxy_input.setText(config.proxy.url)
    window.route_intercept_enabled.setChecked(config.proxy.enable_route_intercept)
    window.headless_enabled.setChecked(config.playwright.headless)
    window.bot_wait_input.setValue(config.bot_protection_wait)
    window.captcha_retry_input.setValue(config.max_captcha_retries)
    window.max_browsers_input.setValue(config.browser_pool.max_browsers)
    window.playwright_path_input.setText(config.playwright.browser_path)
    window.ezcaptcha_input.setText(config.api_keys.ezcaptcha)
    window.sms_activate_input.setText(config.api_keys.sms_activate)
    window.max_risk_input.setValue(config.risk_control.max_consecutive_risk)
    window.max_failure_streak_input.setValue(config.risk_control.max_failure_streak)
    window.max_task_duration_input.setValue(config.risk_control.max_task_duration_seconds)
    window.max_sms_wait_cycles_input.setValue(config.risk_control.max_sms_wait_cycles)
    window.oauth_enabled.setChecked(config.oauth2.enable_oauth2)
    window.client_id_input.setText(config.oauth2.client_id)
    window.redirect_url_input.setText(config.oauth2.redirect_url)
    window.oauth_retry_attempts_input.setValue(config.oauth2.retry_attempts)
    window.oauth_retry_interval_input.setValue(config.oauth2.retry_interval_seconds)
    window.oauth_initial_wait_seconds_input.setValue(config.oauth2.initial_wait_seconds)
    window.oauth_callback_timeout_handled_seconds_input.setValue(config.oauth2.callback_timeout_handled_seconds)
    window.oauth_callback_timeout_unhandled_seconds_input.setValue(config.oauth2.callback_timeout_unhandled_seconds)
    window.oauth_callback_timeout_retry_handled_seconds_input.setValue(config.oauth2.callback_timeout_retry_handled_seconds)
    window.oauth_callback_timeout_retry_unhandled_seconds_input.setValue(config.oauth2.callback_timeout_retry_unhandled_seconds)
    window.scopes_input.setPlainText("\n".join(config.oauth2.scopes))
    window.dynamic_proxy_enabled.setChecked(config.oauth2.dynamic_residential_proxy.enabled)
    window.dynamic_proxy_provider_input.setText(config.oauth2.dynamic_residential_proxy.provider)
    window.dynamic_proxy_mode_input.setCurrentText(config.oauth2.dynamic_residential_proxy.mode)
    window.dynamic_proxy_api_url_input.setText(config.oauth2.dynamic_residential_proxy.api_url)
    window.dynamic_proxy_endpoint_input.setText(config.oauth2.dynamic_residential_proxy.endpoint)
    window.dynamic_proxy_username_input.setText(config.oauth2.dynamic_residential_proxy.username)
    window.dynamic_proxy_password_input.setText(config.oauth2.dynamic_residential_proxy.password)
    window.dynamic_proxy_country_input.setText(config.oauth2.dynamic_residential_proxy.country)
    window.dynamic_proxy_session_input.setText(config.oauth2.dynamic_residential_proxy.session)
    window.dynamic_proxy_sticky_minutes_input.setValue(config.oauth2.dynamic_residential_proxy.sticky_minutes)
    window.mam_enabled_checkbox.setChecked(config.microsoft_account_manager.enabled)
    window.mam_base_url_input.setText(config.microsoft_account_manager.base_url)
    window.mam_ingest_path_input.setText(config.microsoft_account_manager.ingest_path)
    window.mam_ingest_token_input.setText(config.microsoft_account_manager.ingest_token)
    window.mam_upload_after_oauth_checkbox.setChecked(config.microsoft_account_manager.upload_after_oauth)
    window.mam_remark_input.setText(config.microsoft_account_manager.remark)
    window._sync_dynamic_proxy_mode_ui(config.oauth2.dynamic_residential_proxy.mode)
    if hasattr(window, "status_label") and window.status_label is not None:
        try:
            window.status_label.setText(f"已加载配置: {window.loaded_config_path}")
        except RuntimeError:
            pass

    if show_popup:
        QMessageBox.information(window, "重新加载完成", f"已重新加载配置:\n{window.loaded_config_path}")



def get_active_config_path(window) -> Path:
    return Path(getattr(window, "loaded_config_path", CONFIG_PATH) or CONFIG_PATH)



def build_config_from_form(window) -> AppConfig:
    scopes = [
        line.strip()
        for line in window.scopes_input.toPlainText().splitlines()
        if line.strip()
    ]
    config = AppConfig.load(window._get_active_config_path())
    config.choose_browser = window.browser_combo.currentText()
    if hasattr(window, "register_email_domain_combo"):
        config.email_domain = window.register_email_domain_combo.currentText().strip().lower()
        window.email_domain_combo.setCurrentText(config.email_domain)
    else:
        config.email_domain = window.email_domain_combo.currentText().strip().lower()
    config.proxy.url = window.proxy_input.text().strip()
    config.proxy.rotation_url = ""
    config.proxy.enable_route_intercept = window.route_intercept_enabled.isChecked()
    config.bot_protection_wait = window.bot_wait_input.value()
    config.max_captcha_retries = window.captcha_retry_input.value()
    if hasattr(window, "register_concurrent_input"):
        config.concurrent_flows = window.register_concurrent_input.value()
    if hasattr(window, "register_max_tasks_input"):
        config.max_tasks = window.register_max_tasks_input.value()
    config.browser_pool.max_browsers = window.max_browsers_input.value()
    config.playwright.browser_path = window.playwright_path_input.text().strip()
    config.playwright.headless = window.headless_enabled.isChecked()
    config.api_keys.ezcaptcha = window.ezcaptcha_input.text().strip()
    config.api_keys.sms_activate = window.sms_activate_input.text().strip()
    config.risk_control.max_consecutive_risk = window.max_risk_input.value()
    config.risk_control.max_failure_streak = window.max_failure_streak_input.value()
    config.risk_control.max_task_duration_seconds = window.max_task_duration_input.value()
    config.risk_control.max_sms_wait_cycles = window.max_sms_wait_cycles_input.value()
    config.oauth2.enable_oauth2 = window.oauth_enabled.isChecked()
    config.oauth2.client_id = window.client_id_input.text().strip()
    config.oauth2.redirect_url = window.redirect_url_input.text().strip()
    config.oauth2.retry_attempts = window.oauth_retry_attempts_input.value()
    config.oauth2.retry_interval_seconds = window.oauth_retry_interval_input.value()
    config.oauth2.initial_wait_seconds = window.oauth_initial_wait_seconds_input.value()
    config.oauth2.callback_timeout_handled_seconds = window.oauth_callback_timeout_handled_seconds_input.value()
    config.oauth2.callback_timeout_unhandled_seconds = window.oauth_callback_timeout_unhandled_seconds_input.value()
    config.oauth2.callback_timeout_retry_handled_seconds = window.oauth_callback_timeout_retry_handled_seconds_input.value()
    config.oauth2.callback_timeout_retry_unhandled_seconds = window.oauth_callback_timeout_retry_unhandled_seconds_input.value()
    config.oauth2.scopes = scopes
    config.oauth2.dynamic_residential_proxy.enabled = window.dynamic_proxy_enabled.isChecked()
    config.oauth2.dynamic_residential_proxy.provider = window.dynamic_proxy_provider_input.text().strip() or "Kookeey"
    config.oauth2.dynamic_residential_proxy.mode = window.dynamic_proxy_mode_input.currentText().strip().lower()
    config.oauth2.dynamic_residential_proxy.api_url = window.dynamic_proxy_api_url_input.text().strip()
    config.oauth2.dynamic_residential_proxy.endpoint = window.dynamic_proxy_endpoint_input.text().strip()
    config.oauth2.dynamic_residential_proxy.username = window.dynamic_proxy_username_input.text().strip()
    config.oauth2.dynamic_residential_proxy.password = window.dynamic_proxy_password_input.text().strip()
    config.oauth2.dynamic_residential_proxy.country = window.dynamic_proxy_country_input.text().strip()
    config.oauth2.dynamic_residential_proxy.session = window.dynamic_proxy_session_input.text().strip()
    config.oauth2.dynamic_residential_proxy.sticky_minutes = window.dynamic_proxy_sticky_minutes_input.value()
    config.microsoft_account_manager.enabled = window.mam_enabled_checkbox.isChecked()
    config.microsoft_account_manager.base_url = window.mam_base_url_input.text().strip()
    config.microsoft_account_manager.ingest_path = window.mam_ingest_path_input.text().strip() or "/api/upload/ingest"
    config.microsoft_account_manager.ingest_token = window.mam_ingest_token_input.text().strip()
    config.microsoft_account_manager.upload_after_oauth = window.mam_upload_after_oauth_checkbox.isChecked()
    config.microsoft_account_manager.remark = window.mam_remark_input.text().strip() or "OutlookRegister OAuth2"
    return config



def save_form_to_config(window, show_popup: bool = True) -> bool:
    if hasattr(window, "status_label") and window.status_label is not None:
        try:
            window.status_label.setText("正在保存配置...")
        except RuntimeError:
            pass
    QApplication.processEvents()

    try:
        config = window._build_config_from_form()
        config.validate()
        config.save()
    except ConfigValidationError as exc:
        message = "\n".join(exc.errors)
        QMessageBox.warning(window, "配置校验失败", message)
        if hasattr(window, "status_label") and window.status_label is not None:
            try:
                window.status_label.setText(f"配置校验失败: {exc.errors[0] if exc.errors else '未知错误'}")
            except RuntimeError:
                pass
        return False
    except Exception as exc:
        QMessageBox.critical(window, "保存失败", f"保存配置时发生异常:\n{exc}")
        if hasattr(window, "status_label") and window.status_label is not None:
            try:
                window.status_label.setText(f"保存配置失败: {exc}")
            except RuntimeError:
                pass
        return False

    if show_popup:
        QMessageBox.information(window, "保存成功", f"配置已保存到:\n{window._get_active_config_path()}")
    if hasattr(window, "status_label") and window.status_label is not None:
        try:
            window.status_label.setText(f"配置已保存: {window._get_active_config_path()}")
        except RuntimeError:
            pass
    return True
