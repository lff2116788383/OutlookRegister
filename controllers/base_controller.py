import random
import threading
import time
from abc import ABC, abstractmethod
from collections import Counter

from faker import Faker

from app_config import AppConfig
from execution_models import ErrorCode, FlowResult, Stage
from logger import logger
from utils import build_email_address, random_email


class BaseBrowserController(ABC):
    """所有浏览器控制器的公共接口与共享流程。"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.wait_time = config.bot_protection_wait * 1000
        self.max_captcha_retries = config.max_captcha_retries
        self.enable_oauth2 = config.oauth2.enable_oauth2
        self.proxy = config.proxy.url
        self.dynamic_proxy_config = config.oauth2.dynamic_residential_proxy
        self.sms_api_key = config.api_keys.sms_activate
        self.cleanup_lock = threading.Lock()
        self.active_resources = []
        self.browser_pool_size = max(1, min(config.browser_pool.max_browsers, config.concurrent_flows))
        self._browser_pool = []
        self._browser_pool_index = 0
        self.enable_route_intercept = config.proxy.enable_route_intercept

    @abstractmethod
    def launch_browser(self):
        """启动浏览器并返回运行时实例。"""

    @abstractmethod
    def handle_captcha(self, page):
        """验证码处理流程。"""

    @abstractmethod
    def clean_up(self, page=None, type="all_browser"):
        """清理浏览器与页面上下文资源。"""

    @abstractmethod
    def get_thread_page(self):
        """返回当前线程使用的页面对象。"""

    def _init_traffic_stats(self):
        return {
            "request_count": 0,
            "response_count": 0,
            "blocked_count": 0,
            "request_bytes": 0,
            "response_bytes": 0,
            "blocked_types": Counter(),
        }

    def _format_bytes(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        value = float(max(0, size))
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.2f}{unit}"
            value /= 1024
        return f"{value:.2f}GB"

    def _estimate_request_bytes(self, request) -> int:
        total = 0
        try:
            headers = request.headers or {}
            for key, value in headers.items():
                total += len(str(key).encode("utf-8")) + len(str(value).encode("utf-8")) + 4
        except Exception:
            pass
        try:
            post_data = request.post_data or ""
            total += len(str(post_data).encode("utf-8"))
        except Exception:
            pass
        return total

    def _estimate_response_bytes(self, response) -> int:
        total = 0
        try:
            headers = response.headers or {}
            content_length = headers.get("content-length") or headers.get("Content-Length")
            if content_length:
                return max(0, int(content_length))
            for key, value in headers.items():
                total += len(str(key).encode("utf-8")) + len(str(value).encode("utf-8")) + 4
        except Exception:
            pass
        return total

    def _log_traffic_stats(self, stats: dict, email_address: str, stage: str) -> None:
        logger.info(
            "Traffic stats [%s] %s | requests=%s responses=%s blocked=%s upload≈%s download≈%s blocked_types=%s",
            stage,
            email_address,
            stats.get("request_count", 0),
            stats.get("response_count", 0),
            stats.get("blocked_count", 0),
            self._format_bytes(stats.get("request_bytes", 0)),
            self._format_bytes(stats.get("response_bytes", 0)),
            dict(stats.get("blocked_types", {})),
        )

    def get_thread_browser(self):
        with self.cleanup_lock:
            if len(self._browser_pool) < self.browser_pool_size:
                playwright_instance, browser_instance = self.launch_browser()
                if not playwright_instance:
                    return False
                resource = (playwright_instance, browser_instance)
                self._browser_pool.append(resource)
                self.active_resources.append(resource)
                return browser_instance

            resource = self._browser_pool[self._browser_pool_index % len(self._browser_pool)]
            self._browser_pool_index += 1
            return resource[1]

    def _fail(self, error_code: ErrorCode, message: str, stage: Stage, *, risk_detected: bool = False) -> FlowResult:
        logger.error("[%s] %s", error_code.value, message)
        return FlowResult.fail(error_code, message, stage, risk_detected=risk_detected)

    def _is_first_login_ready(self, page) -> bool:
        ready_selectors = [
            '[aria-label="新邮件"]',
            '[aria-label="New mail"]',
            '[data-icon-name="ComposeRegular"]',
            '[data-testid="m365-shell-header"]',
            '#O365_NavHeader',
            '[role="navigation"][aria-label*="Outlook"]',
        ]
        for selector in ready_selectors:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.wait_for(state="visible", timeout=1200)
                    return True
            except Exception:
                continue
        return False

    def _is_first_login_soft_ready(self, page) -> bool:
        current_url = ""
        try:
            current_url = str(page.url or "")
        except Exception:
            current_url = ""

        soft_ready_selectors = [
            '[data-testid="app-shell"]',
            '[data-testid="hero-banner"]',
            '[data-testid="pivot-header"]',
            '[role="main"]',
            '[role="banner"]',
            'button[title*="Outlook"]',
            'button[aria-label*="Outlook"]',
            'text="欢迎使用新版 Outlook"',
            'text="Welcome to the new Outlook"',
            'text="保持登录状态?"',
            'text="Stay signed in?"',
            'text="创建通行密钥"',
            'text="Create a passkey"',
        ]
        for selector in soft_ready_selectors:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    locator.first.wait_for(state="visible", timeout=800)
                    return True
            except Exception:
                continue

        has_login_input = False
        has_password_input = False
        try:
            has_login_input = page.locator('input[name="loginfmt"], #i0116').count() > 0
        except Exception:
            pass
        try:
            has_password_input = page.locator('input[name="passwd"], #i0118').count() > 0
        except Exception:
            pass

        if not has_login_input and not has_password_input and any(host in current_url for host in [
            'outlook.live.com',
            'outlook.office.com',
            'account.microsoft.com',
            'login.live.com',
        ]):
            return True

        return False

    def _dismiss_first_login_prompts(self, page) -> None:
        actions = [
            ("无法创建通行密钥", "取消"),
            ("Can’t create a passkey", "Cancel"),
            ("创建通行密钥", "暂时跳过"),
            ("Create a passkey", "Skip for now"),
            ("欢迎使用新版 Outlook", "稍后"),
            ("Welcome to the new Outlook", "Later"),
            ("保持登录状态?", "否"),
            ("Stay signed in?", "No"),
        ]
        for prompt_text, button_text in actions:
            try:
                if page.get_by_text(prompt_text).count() > 0 and page.get_by_text(button_text).count() > 0:
                    page.get_by_text(button_text).first.click(timeout=4000)
                    page.wait_for_timeout(800)
            except Exception:
                continue

    def ensure_first_login_ready(self, page, email: str, password: str) -> FlowResult:
        email_address = build_email_address(email, self.config.email_domain)
        logger.info("Validating first login readiness for %s", email_address)
        try:
            if self._is_first_login_ready(page):
                return FlowResult.ok(
                    stage=Stage.FIRST_LOGIN.value,
                    metadata={
                        "first_login_confirmed": True,
                        "email_address": email_address,
                    },
                )

            page.goto("https://outlook.live.com/mail/0/", timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            sign_in_candidates = [
                'a[data-task="signin"]',
                'a[href*="login.live.com"]',
                'button[data-testid="hero-sign-in"]',
                'text="登录"',
                'text="Sign in"',
            ]
            for selector in sign_in_candidates:
                try:
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        locator.first.click(timeout=5000, force=True)
                        page.wait_for_timeout(1200)
                        break
                except Exception:
                    continue

            email_input = page.locator('input[name="loginfmt"], input[type="email"], #i0116')
            if email_input.count() > 0:
                email_input.first.wait_for(state="visible", timeout=15000)
                email_input.first.fill(email_address, timeout=10000)
                page.locator('#idSIButton9, button[type="submit"], input[type="submit"]').first.click(timeout=7000)
                page.wait_for_timeout(1000)

            password_input = page.locator('input[name="passwd"], input[type="password"], #i0118')
            if password_input.count() > 0:
                password_input.first.wait_for(state="visible", timeout=15000)
                password_input.first.fill(password, timeout=10000)
                page.locator('#idSIButton9, button[type="submit"], input[type="submit"]').first.click(timeout=7000)
                page.wait_for_timeout(1500)

            self._dismiss_first_login_prompts(page)

            deadline = time.time() + 45
            while time.time() < deadline:
                self._dismiss_first_login_prompts(page)
                if self._is_first_login_ready(page) or self._is_first_login_soft_ready(page):
                    logger.info("First login confirmed for %s", email_address)
                    return FlowResult.ok(
                        stage=Stage.FIRST_LOGIN.value,
                        metadata={
                            "first_login_confirmed": True,
                            "email_address": email_address,
                        },
                    )
                page.wait_for_timeout(1000)

            return self._fail(
                ErrorCode.SELECTOR_NOT_FOUND,
                f"First login confirmation timed out for {email_address}",
                Stage.FIRST_LOGIN,
            )
        except Exception as exc:
            return self._fail(
                ErrorCode.UNKNOWN_ERROR,
                f"First login confirmation failed for {email_address}: {exc}",
                Stage.FIRST_LOGIN,
            )

    def _first_visible_locator(self, page, candidates, timeout=20000):
        deadline = time.time() + timeout / 1000
        while time.time() < deadline:
            for selector in candidates:
                locator = page.locator(selector)
                try:
                    handles = locator.element_handles()
                    if handles:
                        try:
                            handles[0].wait_for_element_state("visible", timeout=500)
                        except Exception:
                            pass
                        logger.info("Matched selector: %s", selector)
                        return locator.first
                except Exception:
                    continue
            page.wait_for_timeout(300)
        raise TimeoutError(f"No visible locator matched: {candidates}")

    def _choose_email_domain(self, page) -> None:
        domain = self.config.email_domain
        trigger_selectors = [
            "#LiveDomainBoxList",
            '[aria-label*="@outlook.com"]',
            '[aria-label*="@hotmail.com"]',
            '[role="combobox"]',
            'button[aria-haspopup="listbox"]',
        ]
        option_selectors = [
            f'option[value="{domain}"]',
            f'[role="option"]:text-is("@{domain}")',
            f'[role="option"]:text-is("{domain}")',
            f'text="@{domain}"',
            f'text="{domain}"',
        ]

        try:
            trigger = None
            for selector in trigger_selectors:
                locator = page.locator(selector)
                if locator.count() > 0:
                    trigger = locator.first
                    break

            if trigger is None:
                logger.warning("Email domain selector not found, skip switching to %s", domain)
                return

            try:
                current_text = (trigger.inner_text(timeout=500) or "").strip().lower()
                if domain in current_text:
                    logger.info("Email domain already set to %s", domain)
                    return
            except Exception:
                pass

            trigger.click(timeout=3000)
            page.wait_for_timeout(300)

            for selector in option_selectors:
                option = page.locator(selector)
                if option.count() > 0:
                    option.first.click(timeout=3000, force=True)
                    logger.info("Email domain switched to %s via %s", domain, selector)
                    return

            logger.warning("Email domain options not found for %s after opening selector", domain)
        except Exception as exc:
            logger.warning("Failed to switch email domain to %s: %s", domain, exc)

    def _is_username_taken(self, page) -> bool:
        messages = [
            "该用户名已被占用",
            "此用户名已被占用",
            "已被占用",
            "已被使用",
            "That username is taken",
            "This username is unavailable",
        ]
        for text in messages:
            try:
                if page.get_by_text(text).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _apply_suggested_username(self, page) -> str | None:
        suggestion_selectors = [
            '[role="button"]',
            'button',
            '[role="option"]',
            'span',
        ]
        for selector in suggestion_selectors:
            locator = page.locator(selector)
            try:
                count = min(locator.count(), 12)
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    text = (item.inner_text(timeout=300) or "").strip()
                except Exception:
                    continue
                if not text:
                    continue
                normalized = text.replace("@", "").replace(self.config.email_domain, "").strip()
                if not normalized:
                    continue
                compact = normalized.replace(" ", "")
                if compact.isalnum() and any(char.isdigit() for char in compact):
                    try:
                        item.click(timeout=1500, force=True)
                        page.wait_for_timeout(400)
                        logger.info("Using suggested username: %s", compact)
                        return compact
                    except Exception:
                        continue
        return None

    def _clear_email_input(self, email_input) -> None:
        try:
            email_input.click(timeout=1000)
            email_input.fill("")
        except Exception:
            try:
                email_input.press("Control+A")
                email_input.press("Backspace")
            except Exception:
                pass

    def _submit_username_with_retries(self, page, email_input, next_btn, email: str) -> str:
        candidate = email
        attempted_candidates = {candidate}

        for attempt in range(6):
            self._clear_email_input(email_input)
            email_input.type(candidate, delay=0.006 * self.wait_time, timeout=10000)
            next_btn.click(timeout=5000, force=True)
            page.wait_for_timeout(1200)

            if not self._is_username_taken(page):
                if attempt > 0:
                    logger.info("Resolved username collision, continue with %s", candidate)
                return candidate

            logger.warning("Username already taken: %s", build_email_address(candidate, self.config.email_domain))

            if attempt == 0:
                suggested = self._apply_suggested_username(page)
                if suggested and suggested not in attempted_candidates:
                    attempted_candidates.add(suggested)
                    candidate = suggested
                    continue

            next_candidate = ""
            for _ in range(10):
                regenerated = generate_unique_email_prefix()
                if regenerated not in attempted_candidates:
                    next_candidate = regenerated
                    break

            if not next_candidate:
                next_candidate = f"{generate_unique_email_prefix()}x{attempt}"

            attempted_candidates.add(next_candidate)
            candidate = next_candidate
            logger.info("Retrying with regenerated unique prefix: %s", candidate)

        raise TimeoutError("Username remained unavailable after retries")


    def outlook_register(self, page, email, password) -> FlowResult:
        fake = Faker()
        final_email = email
        email_address = build_email_address(final_email, self.config.email_domain)
        traffic_stats = getattr(page, "_traffic_stats", None)

        lastname = fake.last_name()
        firstname = fake.first_name()
        year = str(random.randint(1960, 2005))
        month = str(random.randint(1, 12))
        day = str(random.randint(1, 28))

        try:
            logger.info("Navigating to outlook registration for %s", email_address)
            page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=20000, wait_until="domcontentloaded")
            page.get_by_text("同意并继续").wait_for(timeout=30000)
            start_time = time.time()
            page.wait_for_timeout(0.1 * self.wait_time)
            page.get_by_text("同意并继续").click(timeout=30000)
        except Exception as exc:
            return self._fail(
                ErrorCode.PAGE_NAVIGATION_FAILED,
                f"Failed to enter registration page: {exc}",
                Stage.NAVIGATE_REGISTER,
            )

        page.wait_for_timeout(1500)

        try:
            logger.info("Filling account details for %s", email_address)
            self._choose_email_domain(page)

            email_input = self._first_visible_locator(
                page,
                [
                    '[aria-label="新建电子邮件"]',
                    "#MemberName",
                    'input[name="MemberName"]',
                    '[aria-label="New email"]',
                    'input[placeholder="name@example.com"]',
                    'input[placeholder*="@outlook.com"]',
                    'input[type="email"]',
                    'input[aria-describedby*="MemberName"]',
                ],
            )

            next_btn = self._first_visible_locator(
                page,
                [
                    '[data-testid="primaryButton"]',
                    "#iSignupAction",
                    'button[type="submit"]',
                    'input[type="submit"]',
                ],
                timeout=10000,
            )
            final_email = self._submit_username_with_retries(page, email_input, next_btn, email)
            email_address = build_email_address(final_email, self.config.email_domain)

            page.wait_for_timeout(0.02 * self.wait_time)

            pwd_input = self._first_visible_locator(
                page,
                [
                    '[type="password"]',
                    "#PasswordInput",
                    'input[name="Password"]',
                ],
            )
            pwd_input.type(password, delay=0.004 * self.wait_time, timeout=10000)

            page.wait_for_timeout(0.02 * self.wait_time)
            next_btn = self._first_visible_locator(
                page,
                [
                    '[data-testid="primaryButton"]',
                    "#iSignupAction",
                    'button[type="submit"]',
                    'input[type="submit"]',
                ],
                timeout=10000,
            )
            next_btn.click(timeout=5000, force=True)

            page.wait_for_timeout(0.03 * self.wait_time)
            page.locator('[name="BirthYear"]').fill(year, timeout=10000)

            try:
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator('[name="BirthMonth"]').select_option(value=month, timeout=1000)
                page.wait_for_timeout(0.05 * self.wait_time)
                page.locator('[name="BirthDay"]').select_option(value=day, timeout=5000)
            except Exception:
                logger.info("Falling back to manual selection for birth month/day")
                page.locator('[name="BirthMonth"]').click()
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{month}月")').click(force=True)
                page.wait_for_timeout(0.04 * self.wait_time)
                page.locator('[name="BirthDay"]').click()
                page.wait_for_timeout(0.03 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{day}日")').click(force=True)
                page.locator('[data-testid="primaryButton"]').click(timeout=5000, force=True)

            page.locator("#lastNameInput").type(lastname, delay=0.002 * self.wait_time, timeout=10000)
            page.wait_for_timeout(0.02 * self.wait_time)
            page.locator("#firstNameInput").fill(firstname, timeout=10000)

            if time.time() - start_time < self.wait_time / 1000:
                page.wait_for_timeout(self.wait_time - (time.time() - start_time) * 1000)

            page.locator('[data-testid="primaryButton"]').click(timeout=5000, force=True)
            try:
                page.locator('span > [href="https://go.microsoft.com/fwlink/?LinkID=521839"]').wait_for(
                    state="detached",
                    timeout=22000,
                )
            except Exception:
                page.wait_for_timeout(1000)

            has_risk = page.get_by_text("一些异常活动").count() > 0
            has_maintenance = page.get_by_text("此站点正在维护").count() > 0 or page.get_by_text(
                "此站点正在维护，暂时无法使用，请稍后重试。"
            ).count() > 0
            if has_risk or has_maintenance:
                error_code = ErrorCode.RATE_LIMITED if has_risk else ErrorCode.SITE_MAINTENANCE
                message = "IP rate limited" if has_risk else "Site maintenance detected"
                return self._fail(error_code, message, Stage.FILL_PROFILE, risk_detected=True)

            if page.get_by_text("添加电话号码").count() > 0 or page.locator('[id="PhoneNum"]').count() > 0:
                logger.info("SMS verification required for %s", email_address)
                if not self.sms_api_key:
                    return self._fail(
                        ErrorCode.SMS_REQUIRED_NO_KEY,
                        "SMS verification required but SmsActivate key missing",
                        Stage.SMS_VERIFICATION,
                    )

                from services import SmsActivate

                sms = SmsActivate(self.sms_api_key)
                phone_id, phone_num = sms.get_number(service="mm", country=0)
                if not phone_num:
                    return self._fail(
                        ErrorCode.SMS_GET_NUMBER_FAILED,
                        "Failed to get phone number from SMS Activate",
                        Stage.SMS_VERIFICATION,
                    )

                logger.info("Using phone number: %s", phone_num)
                phone_input = page.locator('input[type="tel"]')
                if phone_input.count() == 0:
                    phone_input = page.locator('[id="PhoneNum"]')
                phone_input.fill(phone_num)
                page.locator('[id="iSignupAction"]').click(timeout=10000)

                logger.info("Waiting for SMS code...")
                code = None
                max_sms_wait_cycles = self.config.risk_control.max_sms_wait_cycles
                for _ in range(max_sms_wait_cycles):
                    page.wait_for_timeout(5000)
                    code = sms.get_status(phone_id)
                    if code:
                        break

                if code:
                    logger.info("Received SMS code: %s", code)
                    page.locator('input[id="PhoneProofCode"]').fill(code)
                    page.locator('[id="iSignupAction"]').click(timeout=10000)
                    sms.set_status(phone_id, 6)
                else:
                    sms.set_status(phone_id, 8)
                    return self._fail(
                        ErrorCode.SMS_CODE_TIMEOUT,
                        "SMS code timeout",
                        Stage.SMS_VERIFICATION,
                    )

            captcha_ok = self.handle_captcha(page)
            if not captcha_ok:
                return self._fail(
                    ErrorCode.CAPTCHA_FAILED,
                    f"Captcha solving failed for {email_address}",
                    Stage.CAPTCHA,
                    risk_detected=True,
                )

        except TimeoutError as exc:
            if traffic_stats:
                self._log_traffic_stats(traffic_stats, email_address, "register_failed")
            return self._fail(
                ErrorCode.SELECTOR_NOT_FOUND,
                f"Registration selector timeout: {exc}",
                Stage.FILL_PROFILE,
            )
        except Exception as exc:
            if traffic_stats:
                self._log_traffic_stats(traffic_stats, email_address, "register_failed")
            return self._fail(
                ErrorCode.UNKNOWN_ERROR,
                f"Registration flow interrupted for {email_address}: {exc}",
                Stage.FILL_PROFILE,
            )

        if traffic_stats:
            self._log_traffic_stats(traffic_stats, email_address, "register")
        logger.info("Successfully registered: %s", email_address)

        first_login_result = self.ensure_first_login_ready(page, final_email, password)
        if not first_login_result.success:
            return first_login_result

        return FlowResult.ok(
            stage=Stage.POST_REGISTER.value,
            metadata={
                "final_email": final_email,
                "email_address": email_address,
                "first_login_confirmed": True,
            },
        )
