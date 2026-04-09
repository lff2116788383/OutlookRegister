from __future__ import annotations

from app_config import AppConfig
from controllers.patchright_controller import PatchrightController
from controllers.playwright_controller import PlaywrightController


def build_controller(config: AppConfig):
    if config.choose_browser == "patchright":
        return PatchrightController(config)
    if config.choose_browser == "playwright":
        return PlaywrightController(config)
    raise ValueError("不支持的浏览器类型，填写 patchright 或 playwright")
