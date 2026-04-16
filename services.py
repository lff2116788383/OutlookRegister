from __future__ import annotations
import json
import time
from typing import Any, Dict
from urllib.parse import quote, urlsplit
import urllib.request


import requests
from logger import logger

class EzCaptcha:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.ez-captcha.com"

    def solve_funcaptcha(self, website_url, website_key):
        if not self.api_key:
            logger.error("EzCaptcha API key not configured")
            return None
            
        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "FunCaptchaTaskProxyless",
                "websiteURL": website_url,
                "websitePublicKey": website_key
            }
        }
        try:
            logger.info(f"Creating FunCaptcha task for {website_url}")
            res = requests.post(f"{self.base_url}/createTask", json=payload, timeout=20).json()
            if res.get("errorId") == 0:
                task_id = res.get("taskId")
                logger.info(f"Task created: {task_id}, polling for result...")
                for i in range(30): # 30 * 3s = 90s
                    time.sleep(3)
                    res2 = requests.post(f"{self.base_url}/getTaskResult", json={"clientKey": self.api_key, "taskId": task_id}, timeout=20).json()
                    if res2.get("status") == "ready":
                        logger.info("Captcha solved successfully")
                        return res2.get("solution", {}).get("token")
                    elif res2.get("errorId") != 0:
                        logger.error(f"Captcha polling error: {res2.get('errorDescription')}")
                        break
            else:
                logger.error(f"Captcha task creation failed: {res.get('errorDescription')}")
        except Exception as e:
            logger.error(f"EzCaptcha API error: {e}")
        return None

class SmsActivate:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sms-activate.org/stubs/handler_api.php"

    def get_number(self, service='mm', country=0):
        if not self.api_key:
            logger.error("SmsActivate API key not configured")
            return None, None
            
        params = {
            'api_key': self.api_key,
            'action': 'getNumber',
            'service': service,
            'country': country
        }
        try:
            res = requests.get(self.base_url, params=params, timeout=20).text
            if "ACCESS_NUMBER" in res:
                parts = res.split(':')
                logger.info(f"Obtained phone number: {parts[2]} (ID: {parts[1]})")
                return parts[1], parts[2] 
            else:
                logger.error(f"SmsActivate error: {res}")
        except Exception as e:
            logger.error(f"SmsActivate API error: {e}")
        return None, None

    def get_status(self, activation_id):
        params = {
            'api_key': self.api_key,
            'action': 'getStatus',
            'id': activation_id
        }
        try:
            res = requests.get(self.base_url, params=params, timeout=20).text
            if "STATUS_OK" in res:
                return res.split(':')[1] 
        except Exception:
            pass
        return None

    def set_status(self, activation_id, status):
        params = {
            'api_key': self.api_key,
            'action': 'setStatus',
            'status': status,
            'id': activation_id
        }
        try:
            requests.get(self.base_url, params=params, timeout=20)
        except:
            pass

class ProxyManager:
    def __init__(self, static_proxy=None, dynamic_proxy_config=None):
        self.static_proxy = static_proxy
        self.dynamic_proxy_config = dynamic_proxy_config
        self._cached_dynamic_proxy = None

    @staticmethod
    def _normalize_proxy(raw_proxy: str) -> str:
        raw_proxy = str(raw_proxy or "").strip()
        if not raw_proxy:
            return ""
        if raw_proxy.startswith(("http://", "https://")):
            return raw_proxy
        if "@" in raw_proxy:
            return f"http://{raw_proxy}"

        parts = raw_proxy.split(":")
        if len(parts) >= 4:
            host = parts[0]
            port = parts[1]
            username = parts[2]
            password = ":".join(parts[3:])
            return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"

        return f"http://{raw_proxy}"

    @staticmethod
    def _parse_pick_response(body: str) -> str:
        text = (body or "").strip()
        if not text:
            raise RuntimeError("代理提取接口返回为空")

        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line:
            raise RuntimeError("代理提取接口未返回有效代理")

        if first_line.startswith("{") or first_line.startswith("["):
            payload = json.loads(text)
            data = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(data, list) and data:
                first_item = data[0]
                if isinstance(first_item, dict):
                    ip = str(first_item.get("ip", "") or "")
                    port = str(first_item.get("port", "") or "")
                    username = str(first_item.get("username", "") or "")
                    password = str(first_item.get("password", "") or "")
                    if ip and port and username:
                        return f"{ip}:{port}:{username}:{password}"
                    if ip and port:
                        return f"{ip}:{port}"
            raise RuntimeError("代理提取接口 JSON 返回中未找到可用代理")

        return first_line

    def _fetch_kookeey_proxy(self):
        if not self.dynamic_proxy_config or not self.dynamic_proxy_config.enabled:
            return None

        api_url = str(getattr(self.dynamic_proxy_config, "api_url", "") or "").strip()
        provider = self.dynamic_proxy_config.provider.strip() or "Kookeey"
        if not api_url:
            logger.warning("动态住宅代理已启用，但 %s API 提取链接为空，回退静态代理", provider)
            return None

        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")

        raw_proxy = self._parse_pick_response(body)
        proxy_url = self._normalize_proxy(raw_proxy)
        if not proxy_url:
            raise RuntimeError("Kookeey API 提取后未生成有效代理 URL")

        logger.info("已通过 %s API 提取动态住宅代理: %s", provider, raw_proxy)
        return {
            "provider": provider,
            "raw_proxy": raw_proxy,
            "url_proxy": proxy_url,
            "preserve_raw": False,
            "endpoint": urlsplit(proxy_url).netloc,
        }

    def _parse_direct_proxy(self):
        if not self.dynamic_proxy_config or not self.dynamic_proxy_config.enabled:
            return None

        endpoint = self.dynamic_proxy_config.endpoint.strip()
        username = self.dynamic_proxy_config.username.strip()
        password = self.dynamic_proxy_config.password.strip()
        provider = self.dynamic_proxy_config.provider.strip() or "Kookeey"
        preserve_raw = False

        if "://" in endpoint and not username and not password:
            proxy_url = endpoint
            logger.info("已直接使用 %s 完整代理 URL", provider)
            return {
                "provider": provider,
                "endpoint": urlsplit(proxy_url).netloc,
                "username": urlsplit(proxy_url).username or "",
                "password": urlsplit(proxy_url).password or "",
                "raw_proxy": "",
                "url_proxy": proxy_url,
                "preserve_raw": False,
            }

        if "@" in endpoint and endpoint.count(":") >= 2 and not username and not password:
            credentials, host_part = endpoint.rsplit("@", 1)
            if ":" in credentials:
                username, password = credentials.split(":", 1)
                endpoint = host_part
                logger.info("已从 %s 代理串（username:password@host:port）中解析动态住宅代理配置", provider)
        elif endpoint.count(":") >= 3 and not username and not password:
            raw_proxy = endpoint
            parts = endpoint.split(":")
            endpoint = f"{parts[0]}:{parts[1]}"
            username = parts[2]
            password = ":".join(parts[3:])
            preserve_raw = True
            logger.info("已从 %s 一体化代理串中解析动态住宅代理配置，并保留原始代理格式", provider)

        if not endpoint or not username or not password:
            logger.warning("动态住宅代理已启用，但 %s 直连配置不完整，回退静态代理", provider)
            return None

        raw_proxy = f"{endpoint}:{username}:{password}" if preserve_raw else ""
        url_proxy = f"http://{quote(username, safe='')}:{quote(password, safe='')}@{endpoint}"
        logger.info("已启用 %s 动态住宅代理直连入口: %s", provider, endpoint)
        return {
            "provider": provider,
            "endpoint": endpoint,
            "username": username,
            "password": password,
            "raw_proxy": raw_proxy,
            "url_proxy": url_proxy,
            "preserve_raw": preserve_raw,
        }

    def _resolve_dynamic_proxy(self):
        if not self.dynamic_proxy_config or not self.dynamic_proxy_config.enabled:
            return None

        mode = str(getattr(self.dynamic_proxy_config, "mode", "api") or "api").strip().lower()
        try:
            if mode == "api":
                return self._fetch_kookeey_proxy()
            return self._parse_direct_proxy()
        except Exception as exc:
            provider = self.dynamic_proxy_config.provider.strip() or "Kookeey"
            logger.warning("动态住宅代理获取失败（%s/%s）：%s，回退静态代理", provider, mode, exc)
            return None

    def _build_dynamic_proxy(self, *, refresh: bool = False):
        if refresh:
            self._cached_dynamic_proxy = None

        if self._cached_dynamic_proxy is None:
            self._cached_dynamic_proxy = self._resolve_dynamic_proxy()

        parsed = self._cached_dynamic_proxy
        if not parsed:
            return self.static_proxy
        return parsed["raw_proxy"] if parsed.get("preserve_raw") else parsed["url_proxy"]

    def get_browser_proxy_settings(self):
        proxy_url = self._build_dynamic_proxy()
        if not proxy_url:
            return None

        if self.is_raw_integrated_proxy(proxy_url):
            parts = proxy_url.split(":")
            return {
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": ":".join(parts[3:]),
                "bypass": "localhost",
            }

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

    @staticmethod
    def is_raw_integrated_proxy(proxy_url: str) -> bool:
        return bool(proxy_url and "://" not in proxy_url and "@" not in proxy_url and proxy_url.count(":") >= 3)

    def rotate_if_needed(self):
        return self._build_dynamic_proxy(refresh=True)

    def check_health(self, timeout: int = 15) -> Dict[str, Any]:
        proxy_url = self._build_dynamic_proxy(refresh=True) or self.static_proxy
        result: Dict[str, Any] = {
            "ok": False,
            "proxy_url": proxy_url or "",
            "auth_ok": False,
            "connect_ok": False,
            "ip": "",
            "country": "",
            "country_match": None,
            "sticky_session": None,
            "message": "未配置代理",
        }
        if not proxy_url:
            return result

        result["auth_ok"] = True if self.is_raw_integrated_proxy(proxy_url) else bool(urlsplit(proxy_url).username)

        try:
            if self.is_raw_integrated_proxy(proxy_url):
                proxy_handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
                opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPHandler)
                with opener.open("http://www.ip-api.com/json", timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
            else:
                proxies = {"http": proxy_url, "https": proxy_url}
                response = requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            result["connect_ok"] = True
            result["ok"] = True
            result["ip"] = str(payload.get("ip", payload.get("query", "")) or "")
            result["country"] = str(payload.get("country", payload.get("countryCode", "")) or "")
            expected_country = ""
            sticky_session = ""
            if self.dynamic_proxy_config and self.dynamic_proxy_config.enabled:
                expected_country = str(self.dynamic_proxy_config.country or "").strip().upper()
                sticky_session = str(self.dynamic_proxy_config.session or "").strip()
            result["country_match"] = None if not expected_country else result["country"].upper() == expected_country
            result["sticky_session"] = None if not sticky_session else sticky_session in proxy_url
            result["message"] = "代理连通正常"
            return result
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            result["message"] = f"代理请求失败，HTTP {status_code}"
            return result
        except requests.RequestException as exc:
            result["message"] = f"代理连通失败：{exc}"
            return result
        except Exception as exc:
            result["message"] = f"代理连通失败：{exc}"
            return result

