from __future__ import annotations

import base64
import hashlib
import secrets
import string
import winreg
from datetime import datetime
from urllib.parse import parse_qs, quote

import requests

from app_config import AppConfig


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


def handle_oauth2_form(page, email: str) -> None:
    try:
        page.locator('[name="loginfmt"]').fill(f"{email}@outlook.com", timeout=20000)
        page.locator("#idSIButton9").click(timeout=7000)
        page.locator('[data-testid="appConsentPrimaryButton"]').click(timeout=20000)
    except Exception:
        pass


def get_access_token(page, email: str, config: AppConfig):
    scopes = config.oauth2.scopes
    client_id = config.oauth2.client_id
    redirect_url = config.oauth2.redirect_url

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

    with page.expect_response(lambda response: redirect_url in response.url, timeout=50000) as response_info:
        max_time = 2
        current_times = 0
        while current_times < max_time:
            try:
                page.wait_for_timeout(250)
                url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(
                    f"{key}={quote(value)}" for key, value in params.items()
                )
                page.goto(url)
                break
            except Exception:
                current_times += 1
                if current_times == max_time:
                    return False, False, False
                continue

        handle_oauth2_form(page, email)
        response = response_info.value
        callback_url = response.url

        if "code=" not in callback_url:
            print("Authorization failed: No code in callback URL")
            return False, False, False
        auth_code = parse_qs(callback_url.split("?")[1])["code"][0]

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
        return False, False, False

    refresh_token = payload["refresh_token"]
    access_token = payload.get("access_token", "")
    expire_at = datetime.now().timestamp() + payload["expires_in"]
    return refresh_token, access_token, expire_at
