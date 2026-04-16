from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from threading import Event, Lock
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    BROWSER_LAUNCH_FAILED = "BROWSER_LAUNCH_FAILED"
    PAGE_NAVIGATION_FAILED = "PAGE_NAVIGATION_FAILED"
    SELECTOR_NOT_FOUND = "SELECTOR_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    SITE_MAINTENANCE = "SITE_MAINTENANCE"
    SMS_REQUIRED_NO_KEY = "SMS_REQUIRED_NO_KEY"
    SMS_GET_NUMBER_FAILED = "SMS_GET_NUMBER_FAILED"
    SMS_CODE_TIMEOUT = "SMS_CODE_TIMEOUT"
    CAPTCHA_FAILED = "CAPTCHA_FAILED"
    OAUTH_FAILED = "OAUTH_FAILED"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    RISK_STOPPED = "RISK_STOPPED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class Stage(str, Enum):
    INIT = "init"
    BROWSER = "browser"
    NAVIGATE_REGISTER = "navigate_register"
    FILL_EMAIL = "fill_email"
    FILL_PASSWORD = "fill_password"
    FILL_PROFILE = "fill_profile"
    SMS_VERIFICATION = "sms_verification"
    CAPTCHA = "captcha"
    POST_REGISTER = "post_register"
    FIRST_LOGIN = "first_login"
    OAUTH = "oauth"


@dataclass(slots=True)
class FlowResult:
    success: bool
    error_code: str = ""
    error_message: str = ""
    stage: str = Stage.INIT.value
    risk_detected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, stage: str = Stage.POST_REGISTER.value, metadata: Optional[Dict[str, Any]] = None) -> "FlowResult":
        return cls(success=True, stage=stage, metadata=metadata or {})

    @classmethod
    def fail(
        cls,
        error_code: ErrorCode | str,
        error_message: str,
        stage: Stage | str,
        *,
        risk_detected: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "FlowResult":
        return cls(
            success=False,
            error_code=error_code.value if isinstance(error_code, ErrorCode) else str(error_code),
            error_message=error_message,
            stage=stage.value if isinstance(stage, Stage) else str(stage),
            risk_detected=risk_detected,
            metadata=metadata or {},
        )


class RiskCircuitBreaker:
    def __init__(self, max_consecutive_risk: int = 3, max_failure_streak: int = 5):
        self.max_consecutive_risk = max_consecutive_risk
        self.max_failure_streak = max_failure_streak
        self._lock = Lock()
        self._stop_event = Event()
        self._reason = ""
        self._consecutive_risk = 0
        self._failure_streak = 0

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def stop_reason(self) -> str:
        return self._reason

    def trigger(self, reason: str) -> None:
        with self._lock:
            if not self._stop_event.is_set():
                self._reason = reason
                self._stop_event.set()

    def record_result(self, result: FlowResult) -> None:
        with self._lock:
            if result.success:
                self._consecutive_risk = 0
                self._failure_streak = 0
                return

            self._failure_streak += 1
            if result.risk_detected:
                self._consecutive_risk += 1
            else:
                self._consecutive_risk = 0

            if self._consecutive_risk >= self.max_consecutive_risk:
                self._reason = f"连续风险命中达到阈值: {self._consecutive_risk}"
                self._stop_event.set()
                return

            if self._failure_streak >= self.max_failure_streak:
                self._reason = f"连续失败达到阈值: {self._failure_streak}"
                self._stop_event.set()


@dataclass(slots=True)
class TaskEvent:
    task_id: int
    email: str
    stage: str
    status: str
    message: str
    error_code: str = ""
