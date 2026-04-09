from patchright.sync_api import sync_playwright
from services import EzCaptcha, ProxyManager
from .base_controller import BaseBrowserController
from logger import logger

class PatchrightController(BaseBrowserController):
    def launch_browser(self):
        try:
            # Rotate proxy if configured
            pm = ProxyManager(self.proxy, self.proxy_rotation_url)
            effective_proxy = pm.rotate_if_needed()
            
            p = sync_playwright().start() 

            proxy_settings = {
                "server": effective_proxy,
                "bypass": "localhost",
            } if effective_proxy else None

            logger.info(f"Launching patchright browser (Proxy: {effective_proxy or 'None'})")
            b = p.chromium.launch(
                headless=False,            
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
            if iframe.count() == 0:
                return True

            print("[Info] - 检测到 FunCaptcha 验证码，准备调用 EzCaptcha API")
            if not self.config.api_keys.ezcaptcha:
                print("[Error] - 未配置 ezcaptcha API Key，无法完成验证码识别")
                return False

            src = iframe.get_attribute("src")
            website_key = "B7D8911C-5CC8-A9A3-35B0-554ACEE604DA"
            if src and "pk=" in src:
                website_key = src.split("pk=")[1].split("&")[0]

            ezcaptcha = EzCaptcha(self.config.api_keys.ezcaptcha)
            token = ezcaptcha.solve_funcaptcha("https://outlook.live.com", website_key)
            if not token:
                print("[Error] - 未能获取到 EzCaptcha Token")
                return False

            print("[Info] - 获取到验证码 Token，注入页面...")
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

            if page.get_by_text("一些异常活动").count() or page.get_by_text("此站点正在维护").count() > 0:
                print("[Error: Rate limit] - 正常通过验证码，但当前IP注册频率过快。")
                return False
            return True
        except Exception as exc:
            print(f"[Error: Captcha] - 处理验证码时发生错误: {exc}")
            return False

    def get_thread_page(self):
        browser = self.get_thread_browser()
        context = browser.new_context()
        return context.new_page()

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
