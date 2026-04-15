from __future__ import annotations

from playwright.sync_api import sync_playwright

from logger import logger
from services import EzCaptcha, ProxyManager
from .base_controller import BaseBrowserController


class PlaywrightController(BaseBrowserController):
    def __init__(self, config):
        super().__init__(config)
        self.browser_path = config.playwright.browser_path

    def launch_browser(self):
        try:
            proxy_manager = ProxyManager(self.proxy, self.dynamic_proxy_config)
            effective_proxy = proxy_manager.rotate_if_needed()

            playwright_instance = sync_playwright().start()
            proxy_settings = proxy_manager.get_browser_proxy_settings()

            logger.info("Launching playwright browser (Proxy: %s)", effective_proxy or "None")
            browser_instance = playwright_instance.chromium.launch(
                executable_path=self.browser_path or None,
                headless=self.config.playwright.headless,
                args=["--lang=zh-CN"],
                proxy=proxy_settings,
            )
            return playwright_instance, browser_instance
        except Exception as exc:
            logger.error("Failed to launch playwright browser: %s", exc)
            return False, False

    def get_thread_page(self):
        browser = self.get_thread_browser()
        if not browser:
            return None
        context = browser.new_context()
        page = context.new_page()
        traffic_stats = self._init_traffic_stats()
        setattr(page, "_traffic_stats", traffic_stats)

        page.on("request", lambda request: self._on_request_traffic(request, traffic_stats))
        page.on("response", lambda response: self._on_response_traffic(response, traffic_stats))

        if self.enable_route_intercept:
            page.route("**/*", lambda route, request: self._handle_route(route, request, traffic_stats))
            logger.info("Route intercept enabled for playwright page")

        return page

    def handle_captcha(self, page):
        try:
            iframe = page.locator("iframe#enforcementFrame")
            if iframe.count() == 0:
                return True

            logger.info("Detecting FunCaptcha in playwright")
            ez_api_key = self.config.api_keys.ezcaptcha
            if ez_api_key:
                src = iframe.get_attribute("src")
                website_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
                if src and "pk=" in src:
                    website_key = src.split("pk=")[1].split("&")[0]

                ezcaptcha = EzCaptcha(ez_api_key)
                token = ezcaptcha.solve_funcaptcha("https://outlook.live.com", website_key)
                if not token:
                    return False

                logger.info("Injecting captcha token into playwright page")
                page.evaluate(
                    '''(token) => {
                        window.parent.postMessage(JSON.stringify({
                            eventId: "challenge-complete",
                            payload: { sessionToken: token }
                        }), "*");
                    }''',
                    token,
                )
                page.wait_for_timeout(5000)
                return True

            logger.info("EzCaptcha key missing, fallback to legacy playwright captcha flow")
            page.wait_for_event("request", lambda req: req.url.startswith("blob:https://iframe.hsprotect.net/"), timeout=22000)
            page.wait_for_timeout(800)

            for _ in range(0, self.max_captcha_retries + 1):
                page.keyboard.press('Enter')
                page.wait_for_timeout(11500)
                page.keyboard.press('Enter')

                try:
                    page.wait_for_event("request", lambda req: req.url.startswith("https://browser.events.data.microsoft.com"), timeout=8000)
                    try:
                        page.wait_for_event("request", lambda req: req.url.startswith("https://collector-pxzc5j78di.hsprotect.net/assets/js/bundle"), timeout=1700)
                        page.wait_for_timeout(2000)
                        continue
                    except Exception:
                        if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count() > 0:
                            logger.error("Rate limit after legacy playwright captcha pass")
                            return False
                        break
                except Exception:
                    page.wait_for_timeout(5000)
                    page.keyboard.press('Enter')
                    page.wait_for_event("request", lambda req: req.url.startswith("https://browser.events.data.microsoft.com"), timeout=10000)
                    try:
                        page.wait_for_event("request", lambda req: req.url.startswith("https://collector-pxzc5j78di.hsprotect.net/assets/js/bundle"), timeout=4000)
                    except Exception:
                        break
                    page.wait_for_timeout(500)
            else:
                return False

            return True
        except Exception as exc:
            logger.error("Playwright captcha handling error: %s", exc)
            return False

    def _on_request_traffic(self, request, traffic_stats):
        traffic_stats["request_count"] += 1
        traffic_stats["request_bytes"] += self._estimate_request_bytes(request)

    def _on_response_traffic(self, response, traffic_stats):
        traffic_stats["response_count"] += 1
        traffic_stats["response_bytes"] += self._estimate_response_bytes(response)

    def _handle_route(self, route, request, traffic_stats):
        resource_type = request.resource_type
        if resource_type in {"image", "media", "font"}:
            traffic_stats["blocked_count"] += 1
            traffic_stats["blocked_types"][resource_type] += 1
            route.abort()
            return
        route.continue_()

    def clean_up(self, page=None, type="all_browser"):
        if type == "done_browser" and page:
            try:
                page.context.close()
            except Exception:
                pass
        elif type == "all_browser":
            for playwright_instance, browser_instance in self.active_resources:
                try:
                    browser_instance.close()
                except Exception:
                    pass
                try:
                    playwright_instance.stop()
                except Exception:
                    pass
