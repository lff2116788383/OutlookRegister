from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

CONFIG_PATH = Path("config.json")
RESULTS_DIR = Path("Results")
LOGGED_EMAIL_PATH = RESULTS_DIR / "logged_email.txt"
UNLOGGED_EMAIL_PATH = RESULTS_DIR / "unlogged_email.txt"
OUTLOOK_TOKEN_PATH = RESULTS_DIR / "outlook_token.txt"
APP_LOG_PATH = RESULTS_DIR / "app.log"
TASK_DB_PATH = RESULTS_DIR / "tasks.db"


@dataclass(slots=True)
class OAuth2Config:
    enable_oauth2: bool
    client_id: str
    redirect_url: str
    scopes: List[str]


@dataclass(slots=True)
class ApiKeysConfig:
    ezcaptcha: str
    sms_activate: str


@dataclass(slots=True)
class PlaywrightConfig:
    browser_path: str


@dataclass(slots=True)
class ProxyConfig:
    url: str
    rotation_url: str


@dataclass(slots=True)
class RiskControlConfig:
    max_consecutive_risk: int
    max_failure_streak: int
    max_task_duration_seconds: int
    max_sms_wait_cycles: int


@dataclass(slots=True)
class BrowserPoolConfig:
    max_browsers: int


@dataclass(slots=True)
class AppConfig:
    choose_browser: str
    email_domain: str
    proxy: ProxyConfig
    bot_protection_wait: int
    max_captcha_retries: int
    concurrent_flows: int
    max_tasks: int
    oauth2: OAuth2Config
    api_keys: ApiKeysConfig
    playwright: PlaywrightConfig
    risk_control: RiskControlConfig
    browser_pool: BrowserPoolConfig
    raw: Dict[str, Any]

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppConfig":
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        oauth2 = data.get("oauth2", {})
        api_keys = data.get("api_keys", {})
        playwright = data.get("playwright", {})
        risk_control = data.get("risk_control", {})
        browser_pool = data.get("browser_pool", {})
        proxy_value = data.get("proxy", "")
        proxy_rotation_url = data.get("proxy_rotation_url", "")

        if isinstance(proxy_value, dict):
            proxy_url = proxy_value.get("url", "")
            proxy_rotation_url = proxy_value.get("rotation_url", proxy_rotation_url)
        else:
            proxy_url = str(proxy_value or "")

        email_domain = str(data.get("email_domain", "outlook.com") or "outlook.com").strip().lower()
        if email_domain not in {"hotmail.com", "outlook.com"}:
            email_domain = "outlook.com"

        return cls(
            choose_browser=data.get("choose_browser", "patchright"),
            email_domain=email_domain,
            proxy=ProxyConfig(
                url=proxy_url,
                rotation_url=proxy_rotation_url,
            ),
            bot_protection_wait=int(data.get("bot_protection_wait", 0)),
            max_captcha_retries=int(data.get("max_captcha_retries", 0)),
            concurrent_flows=int(data.get("concurrent_flows", 1)),
            max_tasks=int(data.get("max_tasks", 1)),
            oauth2=OAuth2Config(
                enable_oauth2=bool(oauth2.get("enable_oauth2", False)),
                client_id=oauth2.get("client_id", ""),
                redirect_url=oauth2.get("redirect_url", ""),
                scopes=list(oauth2.get("Scopes", [])),
            ),
            api_keys=ApiKeysConfig(
                ezcaptcha=api_keys.get("ezcaptcha", ""),
                sms_activate=api_keys.get("sms_activate", ""),
            ),
            playwright=PlaywrightConfig(
                browser_path=playwright.get("browser_path", ""),
            ),
            risk_control=RiskControlConfig(
                max_consecutive_risk=int(risk_control.get("max_consecutive_risk", 3)),
                max_failure_streak=int(risk_control.get("max_failure_streak", 5)),
                max_task_duration_seconds=int(risk_control.get("max_task_duration_seconds", 180)),
                max_sms_wait_cycles=int(risk_control.get("max_sms_wait_cycles", 20)),
            ),
            browser_pool=BrowserPoolConfig(
                max_browsers=max(1, int(browser_pool.get("max_browsers", min(int(data.get("concurrent_flows", 1)), 3))))
            ),
            raw=data,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "choose_browser": self.choose_browser,
            "email_domain": self.email_domain,
            "proxy": self.proxy.url,
            "proxy_rotation_url": self.proxy.rotation_url,
            "api_keys": {
                "ezcaptcha": self.api_keys.ezcaptcha,
                "sms_activate": self.api_keys.sms_activate,
            },
            "bot_protection_wait": self.bot_protection_wait,
            "max_captcha_retries": self.max_captcha_retries,
            "concurrent_flows": self.concurrent_flows,
            "max_tasks": self.max_tasks,
            "oauth2": {
                "enable_oauth2": self.oauth2.enable_oauth2,
                "client_id": self.oauth2.client_id,
                "redirect_url": self.oauth2.redirect_url,
                "Scopes": self.oauth2.scopes,
            },
            "playwright": {
                "browser_path": self.playwright.browser_path,
            },
            "risk_control": {
                "max_consecutive_risk": self.risk_control.max_consecutive_risk,
                "max_failure_streak": self.risk_control.max_failure_streak,
                "max_task_duration_seconds": self.risk_control.max_task_duration_seconds,
                "max_sms_wait_cycles": self.risk_control.max_sms_wait_cycles,
            },
            "browser_pool": {
                "max_browsers": self.browser_pool.max_browsers,
            },
            "info": self.raw.get(
                "info",
                "图形界面已启用，运行前请确认配置合法。",
            ),
        }

    def save(self, path: Path = CONFIG_PATH) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(self.to_dict(), file, ensure_ascii=False, indent=4)


def ensure_runtime_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
