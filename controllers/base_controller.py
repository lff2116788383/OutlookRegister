import random
import threading
import time
import json
from abc import ABC, abstractmethod
from faker import Faker
from app_config import AppConfig
from logger import logger

class BaseBrowserController(ABC):
    """所有浏览器控制器的公共接口与共享流程。"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.wait_time = config.bot_protection_wait * 1000
        self.max_captcha_retries = config.max_captcha_retries
        self.enable_oauth2 = config.oauth2.enable_oauth2
        self.proxy = config.proxy.url
        self.proxy_rotation_url = config.proxy.rotation_url
        self.sms_api_key = config.api_keys.sms_activate
        self.thread_local = threading.local()
        self.cleanup_lock = threading.Lock()
        self.active_resources = []

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

    def get_thread_browser(self):
        if not hasattr(self.thread_local, "browser"):
            playwright_instance, browser_instance = self.launch_browser()
            if not playwright_instance:
                return False

            self.thread_local.playwright = playwright_instance
            self.thread_local.browser = browser_instance

            with self.cleanup_lock:
                self.active_resources.append((playwright_instance, browser_instance))

        return self.thread_local.browser

    def outlook_register(self, page, email, password):
        """
        通用逻辑:注册邮箱
        """
        fake = Faker()

        lastname = fake.last_name()
        firstname = fake.first_name()
        year = str(random.randint(1960, 2005))
        month = str(random.randint(1, 12))
        day = str(random.randint(1, 28))

        try:
            logger.info(f"Navigating to outlook registration for {email}@outlook.com")
            page.goto("https://outlook.live.com/mail/0/?prompt=create_account", timeout=20000, wait_until="domcontentloaded")
            page.get_by_text('同意并继续').wait_for(timeout=30000)
            start_time = time.time()
            page.wait_for_timeout(0.1 * self.wait_time)
            page.get_by_text('同意并继续').click(timeout=30000)

        except Exception as e:
            logger.error(f"Failed to enter registration page: {e}")
            return False

        page.wait_for_timeout(1500)
        
        try:
            logger.info(f"Filling account details for {email}")

            def first_visible_locator(candidates, timeout=20000):
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

            email_input = first_visible_locator(
                [
                    '[aria-label="新建电子邮件"]',
                    '#MemberName',
                    'input[name="MemberName"]',
                    '[aria-label="New email"]',
                    'input[placeholder="name@example.com"]',
                    'input[placeholder*="@outlook.com"]',
                    'input[type="email"]',
                    'input[aria-describedby*="MemberName"]',
                ]
            )
            email_input.type(email, delay=0.006 * self.wait_time, timeout=10000)

            next_btn = first_visible_locator(
                [
                    '[data-testid="primaryButton"]',
                    '#iSignupAction',
                    'button[type="submit"]',
                    'input[type="submit"]',
                ],
                timeout=10000,
            )
            next_btn.click(timeout=5000)

            page.wait_for_timeout(0.02 * self.wait_time)

            pwd_input = first_visible_locator(
                [
                    '[type="password"]',
                    '#PasswordInput',
                    'input[name="Password"]',
                ]
            )
            pwd_input.type(password, delay=0.004 * self.wait_time, timeout=10000)

            page.wait_for_timeout(0.02 * self.wait_time)
            next_btn = first_visible_locator(
                [
                    '[data-testid="primaryButton"]',
                    '#iSignupAction',
                    'button[type="submit"]',
                    'input[type="submit"]',
                ],
                timeout=10000,
            )
            next_btn.click(timeout=5000)
            
            page.wait_for_timeout(0.03 * self.wait_time)
            page.locator('[name="BirthYear"]').fill(year, timeout=10000)

            try:
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator('[name="BirthMonth"]').select_option(value=month, timeout=5000)
                page.wait_for_timeout(0.05 * self.wait_time)
                page.locator('[name="BirthDay"]').select_option(value=day, timeout=5000)
            except Exception:
                logger.info("Falling back to manual selection for birth month/day")
                page.locator('[name="BirthMonth"]').click()
                page.wait_for_timeout(0.02 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{month}月")').click()
                page.wait_for_timeout(0.04 * self.wait_time)
                page.locator('[name="BirthDay"]').click()
                page.wait_for_timeout(0.03 * self.wait_time)
                page.locator(f'[role="option"]:text-is("{day}日")').click()
                page.locator('[data-testid="primaryButton"]').click(timeout=5000)

            page.locator('#lastNameInput').type(lastname, delay=0.002 * self.wait_time, timeout=10000)
            page.wait_for_timeout(0.02 * self.wait_time)
            page.locator('#firstNameInput').fill(firstname, timeout=10000)

            if time.time() - start_time < self.wait_time / 1000:
                page.wait_for_timeout(self.wait_time - (time.time() - start_time) * 1000)
            
            page.locator('[data-testid="primaryButton"]').click(timeout=5000)
            
            # Wait for any post-submission blockers
            page.wait_for_timeout(1000)

            if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护').count() > 0:
                logger.error(f"IP Rate limited or site maintenance for {email}")
                return False

            # SMS Verification handling
            if page.get_by_text('添加电话号码').count() > 0 or page.locator('[id="PhoneNum"]').count() > 0:
                logger.info(f"SMS verification required for {email}")
                if not self.sms_api_key:
                    logger.info("SMS Activate key missing, fallback to legacy behavior and mark as failed")
                    return False

                from services import SmsActivate
                sms = SmsActivate(self.sms_api_key)
                phone_id, phone_num = sms.get_number(service='mm', country=0)
                if not phone_num:
                    logger.error("Failed to get phone number from SMS Activate")
                    return False

                logger.info(f"Using phone number: {phone_num}")
                phone_input = page.locator('input[type="tel"]')
                if phone_input.count() == 0:
                    phone_input = page.locator('[id="PhoneNum"]')
                phone_input.fill(phone_num)
                page.locator('[id="iSignupAction"]').click(timeout=10000)

                logger.info("Waiting for SMS code...")
                code = None
                for _ in range(20):
                    page.wait_for_timeout(5000)
                    code = sms.get_status(phone_id)
                    if code:
                        break

                if code:
                    logger.info(f"Received SMS code: {code}")
                    page.locator('input[id="PhoneProofCode"]').fill(code)
                    page.locator('[id="iSignupAction"]').click(timeout=10000)
                    sms.set_status(phone_id, 6)
                else:
                    logger.error("SMS code timeout")
                    sms.set_status(phone_id, 8)
                    return False

            # Captcha handling
            if not self.handle_captcha(page):
                logger.error(f"Captcha solving failed for {email}")
                return False

        except Exception as e:
            logger.error(f"Registration flow interrupted for {email}: {e}")
            return False 
        
        logger.info(f"Successfully registered: {email}@outlook.com")
        from app_config import LOGGED_EMAIL_PATH, UNLOGGED_EMAIL_PATH
        filename = LOGGED_EMAIL_PATH if self.enable_oauth2 else UNLOGGED_EMAIL_PATH
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(f"{email}@outlook.com: {password}\n")

        if not self.enable_oauth2:
            return True
        
        try:
            cancel_btn = page.get_by_text('取消')
            if cancel_btn.count() > 0:
                cancel_btn.click(timeout=10000)
            
            # Handling passkey popup
            if page.get_by_text('无法创建通行密钥').count() > 0:
                 page.get_by_text('取消').click(timeout=7000)

            page.locator('[aria-label="新邮件"]').wait_for(timeout=26000)
            return True

        except Exception as e:
            logger.warning(f"Registered {email} but failed to enter inbox: {e}")
            return True # Still count as success since account is created
