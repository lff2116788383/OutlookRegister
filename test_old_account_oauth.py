from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from app_config import AppConfig, CONFIG_PATH
from get_token import generate_code_challenge, generate_code_verifier
from logger import logger
from services import ProxyManager


def normalize_email_input(raw_email: str, config: AppConfig) -> tuple[str, str]:
    value = str(raw_email or "").strip()
    if not value:
        raise ValueError("邮箱不能为空")

    if "@" in value:
        prefix, _, domain = value.partition("@")
        prefix = prefix.strip()
        domain = domain.strip().lower()
        if not prefix:
            raise ValueError("邮箱前缀不能为空")
        if domain not in {"outlook.com", "hotmail.com"}:
            raise ValueError("当前脚本仅支持 Outlook/Hotmail 个人账号")
        return prefix, f"{prefix}@{domain}"

    prefix = value
    return prefix, f"{prefix}@{config.email_domain}"


def build_browser_proxy_settings(proxy_url: str | None):
    if not proxy_url:
        return None

    from urllib.parse import urlsplit

    split = urlsplit(proxy_url)
    server = f"{split.scheme}://{split.hostname}:{split.port}" if split.hostname and split.port else proxy_url
    settings = {
        "server": server,
        "bypass": "localhost",
    }
    if split.username:
        settings["username"] = split.username
    if split.password:
        settings["password"] = split.password
    return settings


def extract_oauth_error_snapshot(page) -> tuple[str, str]:
    current_url = ""
    try:
        current_url = str(page.url or "")
    except Exception:
        current_url = ""

    text_parts: list[str] = []
    selectors = [
        "body",
        "#error",
        "#message",
        "#usernameError",
        "#passwordError",
        "#idDiv_SAOTCAS_Title",
        "#idDiv_SAOTCC_Title",
        ".error",
        "[role='alert']",
        "[data-testid='error-message']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                text = (locator.first.inner_text(timeout=500) or "").strip()
                if text and text not in text_parts:
                    text_parts.append(text)
        except Exception:
            continue

    snapshot = "\n".join(text_parts)
    match = re.search(r"AADSTS\d+", snapshot, flags=re.IGNORECASE)
    error_code = match.group(0).upper() if match else ""

    known_patterns = [
        r"AADSTS\d+",
        r"redirect_uri[^\n]{0,120}",
        r"unauthorized_client[^\n]{0,120}",
        r"invalid_scope[^\n]{0,120}",
        r"application[^\n]{0,120}not found[^\n]{0,120}",
        r"Microsoft account doesn't exist[^\n]{0,120}",
        r"We couldn't find an account[^\n]{0,120}",
        r"个人 Microsoft 帐户[^\n]{0,120}",
        r"personal Microsoft accounts[^\n]{0,120}",
        r"帐户已锁定[^\n]{0,120}",
        r"account has been locked[^\n]{0,120}",
        r"Abuse[^\n]{0,120}",
    ]
    summary_lines: list[str] = []
    for pattern in known_patterns:
        for found in re.finditer(pattern, snapshot, flags=re.IGNORECASE):
            line = found.group(0).strip()
            if line and line not in summary_lines:
                summary_lines.append(line)

    if not summary_lines and snapshot:
        summary_lines = [line.strip() for line in snapshot.splitlines() if line.strip()][:8]

    summary = "\n".join(summary_lines)
    return error_code, f"当前 URL: {current_url}\n{summary}".strip()


def build_authorize_url(config: AppConfig) -> tuple[str, str]:
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    scope = " ".join(config.oauth2.scopes)
    params = {
        "client_id": config.oauth2.client_id,
        "response_type": "code",
        "redirect_uri": config.oauth2.redirect_url,
        "scope": scope,
        "response_mode": "query",
        "prompt": "select_account",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    from urllib.parse import quote

    url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + "&".join(
        f"{key}={quote(value)}" for key, value in params.items()
    )
    return url, code_verifier


def click_first_visible(page, selectors: list[str], timeout: int = 2500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.wait_for(state="visible", timeout=timeout)
                locator.first.click(timeout=timeout)
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    return False



def auto_fill_oauth_form(page, full_email: str, password: str) -> None:
    try:
        email_input = page.locator('input[name="loginfmt"], #i0116, input[type="email"]')
        if email_input.count() > 0:
            email_input.first.wait_for(state="visible", timeout=5000)
            current_value = (email_input.first.input_value(timeout=500) or "").strip()
            if current_value != full_email:
                email_input.first.fill(full_email, timeout=10000)
            click_first_visible(page, ['#idSIButton9', 'button[type="submit"]', 'input[type="submit"]'])
    except Exception:
        pass

    try:
        password_input = page.locator('input[name="passwd"], #i0118, input[type="password"]')
        if password_input.count() > 0:
            password_input.first.wait_for(state="visible", timeout=5000)
            current_value = (password_input.first.input_value(timeout=500) or "").strip()
            if not current_value:
                password_input.first.fill(password, timeout=10000)
            click_first_visible(page, ['#idSIButton9', 'button[type="submit"]', 'input[type="submit"]'])
    except Exception:
        pass

    click_first_visible(page, [
        'input[type="submit"][value="Yes"]',
        'input[type="submit"][value="Accept"]',
        '#acceptButton',
        '#idSIButton9',
        '#declineButton + #acceptButton',
    ])

    button_texts = ["接受", "Accept", "是", "Yes", "下一步", "Next", "同意", "Allow", "继续"]
    for text in button_texts:
        try:
            button = page.get_by_text(text, exact=True)
            if button.count() > 0:
                button.first.click(timeout=2500)
                page.wait_for_timeout(800)
        except Exception:
            continue



def run_interactive_login_test(page, email: str, password: str, timeout_seconds: int = 45) -> tuple[bool, str]:
    login_url = "https://login.live.com/"
    page.goto(login_url, wait_until="domcontentloaded")
    end_time = time.time() + timeout_seconds

    while time.time() < end_time:
        auto_fill_oauth_form(page, email, password)
        current_url = str(page.url or "")
        lower_url = current_url.lower()

        if any(host in lower_url for host in [
            "account.microsoft.com",
            "outlook.live.com",
            "login.live.com/login.srf",
            "login.live.com/ppsecure/",
        ]):
            try:
                if page.locator('input[name="passwd"], #i0118, input[type="password"]').count() == 0:
                    return True, current_url
            except Exception:
                return True, current_url

        error_code, error_summary = extract_oauth_error_snapshot(page)
        if error_code or "找不到使用该用户名的帐户" in error_summary or "We couldn't find an account" in error_summary:
            return False, error_summary or current_url

        page.wait_for_timeout(800)

    error_code, error_summary = extract_oauth_error_snapshot(page)
    return False, error_summary or str(page.url or "")


def run_old_account_oauth_test(config_path: Path = CONFIG_PATH) -> int:
    config = AppConfig.load(config_path)
    config.validate()

    raw_email = input("请输入老号完整邮箱地址（也可只填前缀）：").strip()
    try:
        _email_prefix, normalized_email = normalize_email_input(raw_email, config)
    except ValueError as exc:
        print(str(exc))
        return 1

    password = input("请输入老号密码：").strip()
    if not password:
        print("密码不能为空")
        return 1

    print(f"当前配置文件: {config_path}")
    print(f"client_id: {config.oauth2.client_id}")
    print(f"redirect_url: {config.oauth2.redirect_url}")
    print(f"测试邮箱: {normalized_email}")
    print("先执行老号直接登录测试，再执行 OAuth 测试...")

    proxy_manager = ProxyManager(config.proxy.url, config.oauth2.dynamic_residential_proxy)
    effective_proxy = proxy_manager.rotate_if_needed()
    print(f"浏览器代理: {effective_proxy or 'None'}")

    page = None
    with sync_playwright() as playwright:
        browser = None
        try:
            proxy_settings = build_browser_proxy_settings(effective_proxy)
            browser = playwright.chromium.launch(
                executable_path=config.playwright.browser_path or None,
                headless=config.playwright.headless,
                args=["--lang=zh-CN"],
                proxy=proxy_settings,
            )
            context = browser.new_context()
            page = context.new_page()

            login_ok, login_detail = run_interactive_login_test(page, normalized_email, password)
            if login_ok:
                print("老号直接登录测试成功")
                print(f"登录后 URL: {login_detail}")
            else:
                print("老号直接登录测试失败")
                print(login_detail or "未获取到明确失败信息")
                print("这通常更像是账号本身不存在、账号被风控、输入有误，或当前 IP/地区触发了微软前置拦截。")
                return 2

            authorize_url, _code_verifier = build_authorize_url(config)
            page.goto(authorize_url, wait_until="domcontentloaded")
            auto_fill_oauth_form(page, normalized_email, password)

            end_time = time.time() + 45
            while time.time() < end_time:
                auto_fill_oauth_form(page, normalized_email, password)
                current_url = str(page.url or "")
                if config.oauth2.redirect_url in current_url:
                    print("OAuth 测试成功：已跳转回 redirect_url")
                    print(f"回调 URL: {current_url}")
                    return 0
                page.wait_for_timeout(800)

            error_code, error_summary = extract_oauth_error_snapshot(page)
            print("OAuth 测试失败：未跳转到 redirect_url")
            print(f"微软错误码: {error_code or '未识别'}")
            print("微软错误摘要:")
            print(error_summary or "未提取到明确错误信息")
            print("如果直接登录成功但 OAuth 失败，优先检查 Azure 应用支持的帐户类型、redirect URI、scope 权限。")
            return 3
        except Exception as exc:
            logger.exception("老号 OAuth 测试异常: %s", exc)
            if page is not None:
                error_code, error_summary = extract_oauth_error_snapshot(page)
                print(f"微软错误码: {error_code or '未识别'}")
                print("微软错误摘要:")
                print(error_summary or "未提取到明确错误信息")
            print(f"OAuth 测试异常: {exc}")
            return 4
        finally:
            try:
                if browser is not None:
                    browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(run_old_account_oauth_test())
