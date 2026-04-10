import random
from patchright.sync_api import sync_playwright
from services import EzCaptcha, ProxyManager
from .base_controller import BaseBrowserController
from logger import logger

class PatchrightController(BaseBrowserController):
    def launch_browser(self):
        try:
            pm = ProxyManager(self.proxy, self.dynamic_proxy_config)
            effective_proxy = pm.rotate_if_needed()
            
            p = sync_playwright().start() 

            proxy_settings = {
                "server": effective_proxy,
                "bypass": "localhost",
            } if effective_proxy else None

            logger.info(f"Launching patchright browser (Proxy: {effective_proxy or 'None'})")
            b = p.chromium.launch(
                headless=self.config.playwright.headless,
                args=['--lang=zh-CN'],
                proxy=proxy_settings
            )

            return p, b

        except Exception as e:
            logger.error(f"Failed to launch browser: {e}")
            return False, False

    def handle_captcha(self, page):
        try:
            iframe = page.locator("iframe#enforcementFrame")
            if iframe.count() > 0:
                logger.info("Detected FunCaptcha challenge in patchright")
                if self.config.api_keys.ezcaptcha:
                    src = iframe.get_attribute("src")
                    website_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
                    if src and "pk=" in src:
                        website_key = src.split("pk=")[1].split("&")[0]

                    ezcaptcha = EzCaptcha(self.config.api_keys.ezcaptcha)
                    token = ezcaptcha.solve_funcaptcha("https://outlook.live.com", website_key)
                    if not token:
                        logger.error("Failed to acquire EzCaptcha token")
                        return False

                    logger.info("Injecting EzCaptcha token into patchright page")
                    page.evaluate(
                        '''(token) => {
                            var input = document.createElement("input");
                            input.type = "hidden";
                            input.name = "FC-Token";
                            input.id = "FC-Token";
                            input.value = token;
                            document.body.appendChild(input);

                            window.parent.postMessage(JSON.stringify({
                                eventId: "challenge-complete",
                                payload: { sessionToken: token }
                            }), "*");
                        }''',
                        token,
                    )
                    page.wait_for_timeout(5000)
                else:
                    logger.info("EzCaptcha key missing, fallback to legacy patchright captcha flow")
                    frame1 = page.frame_locator('iframe[title="验证质询"]')
                    frame2 = frame1.frame_locator('iframe[style*="display: block"]')

                    for _ in range(0, self.max_captcha_retries + 1):
                        page.wait_for_timeout(200)
                        loc = frame2.locator('[aria-label="可访问性挑战"]')
                        box = loc.bounding_box()
                        if not box:
                            logger.error("Legacy captcha accessibility challenge not found")
                            return False
                        x = box['x'] + box['width'] / 2 + random.randint(-10, 10)
                        y = box['y'] + box['height'] / 2 + random.randint(-10, 10)
                        page.mouse.click(x, y)

                        loc2 = frame2.locator('[aria-label="再次按下"]')
                        box2 = loc2.bounding_box()
                        if not box2:
                            logger.error("Legacy captcha second press target not found")
                            return False
                        x = box2['x'] + box2['width'] / 2 + random.randint(-20, 20)
                        y = box2['y'] + box2['height'] / 2 + random.randint(-13, 13)
                        page.mouse.click(x, y)

                        try:
                            page.locator('.draw').wait_for(state="detached")
                            try:
                                page.locator('[role="status"][aria-label="正在加载..."]').wait_for(timeout=5000)
                                page.wait_for_timeout(8000)
                                if page.get_by_text('一些异常活动').count() or page.get_by_text('此站点正在维护，暂时无法使用，请稍后重试。').count() > 0:
                                    logger.error("Rate limit after legacy patchright captcha pass")
                                    return False
                                elif frame2.locator('[aria-label="可访问性挑战"]').count() > 0:
                                    continue
                                break
                            except Exception:
                                if page.get_by_text('取消').count() > 0:
                                    break
                                frame1.get_by_text("请再试一次").wait_for(timeout=15000)
                                continue
                        except Exception:
                            if page.get_by_text('取消').count() > 0:
                                break
                            return False
                    else:
                        return False

            if page.get_by_text("一些异常活动").count() or page.get_by_text("此站点正在维护").count() > 0:
                logger.error("Rate limited or site under maintenance after captcha handling")
                return False
            return True
        except Exception as exc:
            logger.error("Patchright captcha handling error: %s", exc)
            return False

    def get_thread_page(self):
        browser = self.get_thread_browser()
        context = browser.new_context()
        page = context.new_page()
        traffic_stats = self._init_traffic_stats()
        setattr(page, "_traffic_stats", traffic_stats)

        page.on("request", lambda request: self._on_request_traffic(request, traffic_stats))
        page.on("response", lambda response: self._on_response_traffic(response, traffic_stats))

        if self.enable_route_intercept:
            page.route("**/*", lambda route, request: self._handle_route(route, request, traffic_stats))
            logger.info("Route intercept enabled for patchright page")

        return page

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
            context = page.context
            context.close()
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
