from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app_config import AppConfig
from result_store import ResultStore


class SupportsCleanUp(Protocol):
    enable_oauth2: bool

    def get_thread_page(self): ...
    def outlook_register(self, page, email: str, password: str) -> bool: ...
    def clean_up(self, page=None, type: str = "all_browser") -> None: ...


@dataclass(slots=True)
class RuntimeContext:
    config: AppConfig
    result_store: ResultStore
