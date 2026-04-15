from __future__ import annotations

import base64
import hashlib
import secrets
import string
import time
import winreg
from datetime import datetime
from urllib.parse import parse_qs, quote

import requests

from app_config import AppConfig
from logger import logger
from utils import build_email_address


def get_proxy():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as key:
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if proxy_enable and proxy_server:
                return {
                    "http": f"http://{proxy_server}",
                    "https": f"http://{proxy_server}",
                }
    except OSError:
        pass
    return {"http": None, "https": None}


def generate_code_verifier(length: int = 128) -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_code_challenge(code_verifier: str) -> str:
    sha256_hash = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(sha256_hash).decode().rstrip("=")


def handle_oauth2_form(page, email: str, config: AppConfig) -> bool:
    email_address = build_email_address(email, config.email_domain)
    handled = False

    try:
        login_input = page.locator('[name="loginfmt"]')
        if login_input.count() > 0:
            login_input.first.wait_for(state="visible", timeout=8000)
            login_input.first.fill(email_address, timeout=10000)
            page.locator("#idSIButton9").click(timeout=7000)
            handled = True
            page.wait_for_timeout(800)
    except Exception:
        pass

    try:
        password_input = page.locator('[name="passwd"]')
        if password_input.count() > 0:
            logger.warning("OAuth page still requests password for %s", email_address)
            return handled
    except Exception:
        pass

    try:
        consent_button = page.locator('[data-testid="appConsentPrimaryButton"]')
        if consent_button.count() > 0:
            consent_button.first.click(timeout=20000)
            handled = True
            page.wait_for_timeout(800)
    except Exception:
        pass

    try:
        accept_button = page.locator("#idSIButton9")
        if accept_button.count() > 0:
            button_text = (accept_button.first.inner_text(timeout=500) or "").strip()
            if button_text in {"接受", "Accept", "是", "Yes", "下一步", "Next"}:
                accept_button.first.click(timeout=5000)
                handled = True
                page.wait_for_timeout(800)
    except Exception:
        pass

    return handled


def _extract_auth_code_from_url(callback_url: str) -> str | None:
    if "code=" not in callback_url or "?" not in callback_url:
        return None
    try:
        return parse_qs(callback_url.split("?", 1)[1]).get("code", [None])[0]
    except Exception:
        return None


def _is_oauth_account_not_ready(page) -> bool:
    messages = [
        "找不到使用该用户名的帐户",
        "We couldn't find an account with that username",
        "This username may be incorrect",
        "该 Microsoft 帐户不存在",
        "That Microsoft account doesn't exist",
        "请输入有效的电子邮件地址、电话号码或 Skype 用户名",
    ]
    for message in messages:
        try:
            if page.get_by_text(message).count() > 0:
                return True
        except Exception:
            continue
    return False



def _wait_for_oauth_callback(page, redirect_url: str, timeout_ms: int = 15000) -> str | None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        current_url = page.url or ""
        if redirect_url in current_url:
            return current_url
        page.wait_for_timeout(500)
    return None


def get_access_token(page, email: str, config: AppConfig):
    scopes = config.oauth2.scopes
    client_id = config.oauth2.client_id
    redirect_url = config.oauth2.redirect_url
    email_address = build_email_address(email, config.email_domain)

    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    scope = " ".join(scopes)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_url,
        "scope": scope,
        "response_mode": "query",
        "prompt": "select_account",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(
        f"{key}={quote(value)}" for key, value in params.items()
    )

    auth_code = None
    max_attempts = max(2, config.oauth2.retry_attempts)
    retry_interval_ms = config.oauth2.retry_interval_seconds * 1000
    initial_wait_ms = config.oauth2.initial_wait_seconds * 1000
    callback_timeout_handled_ms = config.oauth2.callback_timeout_handled_seconds * 1000
    callback_timeout_unhandled_ms = config.oauth2.callback_timeout_unhandled_seconds * 1000
    callback_timeout_retry_handled_ms = config.oauth2.callback_timeout_retry_handled_seconds * 1000
    callback_timeout_retry_unhandled_ms = config.oauth2.callback_timeout_retry_unhandled_seconds * 1000
    account_ready_wait_ms = max(15000, retry_interval_ms)

    logger.info("Waiting for newly registered account to propagate before OAuth for %s", email_address)
    page.wait_for_timeout(account_ready_wait_ms)

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Starting OAuth authorization attempt %s/%s for %s", attempt, max_attempts, email_address)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(initial_wait_ms)

            handled = handle_oauth2_form(page, email, config)
            callback_url = _wait_for_oauth_callback(
                page,
                redirect_url,
                timeout_ms=callback_timeout_handled_ms if handled else callback_timeout_unhandled_ms,
            )
            if callback_url:
                auth_code = _extract_auth_code_from_url(callback_url)
                if auth_code:
                    break

            handled = handle_oauth2_form(page, email, config)
            callback_url = _wait_for_oauth_callback(
                page,
                redirect_url,
                timeout_ms=callback_timeout_retry_handled_ms if handled else callback_timeout_retry_unhandled_ms,
            )
            if callback_url:
                auth_code = _extract_auth_code_from_url(callback_url)
                if auth_code:
                    break

            if _is_oauth_account_not_ready(page):
                logger.warning("OAuth account not ready yet for %s on attempt %s", email_address, attempt)
                if attempt < max_attempts:
                    page.wait_for_timeout(account_ready_wait_ms)
                continue

            logger.warning("OAuth redirect not reached for %s on attempt %s", email_address, attempt)
        except Exception as exc:
            logger.warning("OAuth authorization attempt %s failed for %s: %s", attempt, email_address, exc)

        if attempt < max_attempts:
            page.wait_for_timeout(retry_interval_ms)

    if not auth_code:
        return False, False, False

    token_data = {
        "client_id": client_id,
        "code": auth_code,
        "redirect_uri": redirect_url,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
        "scope": scope,
    }

    response = requests.post(
        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        proxies=get_proxy(),
    )

    payload = response.json()
    if "refresh_token" not in payload:
        logger.warning("OAuth token response missing refresh_token for %s: %s", email_address, payload)
        return False, False, False

    refresh_token = payload["refresh_token"]
    access_token = payload.get("access_token", "")
    expire_at = datetime.now().timestamp() + payload["expires_in"]
    return refresh_token, access_token, expire_at

