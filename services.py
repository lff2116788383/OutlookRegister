from __future__ import annotations
import time
from typing import Any, Dict
from urllib.parse import urlsplit
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

    def _parse_ipfoxy_proxy(self):
        if not self.dynamic_proxy_config or not self.dynamic_proxy_config.enabled:
            return None

        endpoint = self.dynamic_proxy_config.endpoint.strip()
        username = self.dynamic_proxy_config.username.strip()
        password = self.dynamic_proxy_config.password.strip()
        provider = self.dynamic_proxy_config.provider.strip() or "IPFoxy"
        preserve_raw = False

        if "@" in endpoint and endpoint.count(":") >= 2 and not username and not password:
            credentials, host_part = endpoint.rsplit("@", 1)
            if ":" in credentials:
                username, password = credentials.split(":", 1)
                endpoint = host_part
                logger.info("已从 %s 官方代理串（username:password@host:port）中解析动态住宅代理配置", provider)
        elif endpoint.count(":") >= 3 and not username and not password:
            raw_proxy = endpoint
            parts = endpoint.split(":")
            endpoint = f"{parts[0]}:{parts[1]}"
            username = parts[2]
            password = ":".join(parts[3:])
            preserve_raw = True
            logger.info("已从 %s 一体化代理串中解析动态住宅代理配置，并保留原始代理格式", provider)

        if not endpoint or not username or not password:
            logger.warning("动态住宅代理已启用，但 %s 配置不完整，回退静态代理", provider)
            return None

        proxy_username = username
        if not preserve_raw:
            session = self.dynamic_proxy_config.session.strip()
            country = self.dynamic_proxy_config.country.strip().upper()
            sticky_minutes = max(1, int(getattr(self.dynamic_proxy_config, "sticky_minutes", 30) or 30))
            tags = []
            if country and "-cc-" not in proxy_username:
                tags.append(f"cc-{country}")
            session_tag = session
            if session_tag and sticky_minutes:
                session_tag = f"{session_tag}_{sticky_minutes * 1000}"
            if session_tag and "-sessid-" not in proxy_username:
                tags.append(f"sessid-{session_tag}")
            if sticky_minutes and "-ttl-" not in proxy_username:
                tags.append(f"ttl-{sticky_minutes}")
            if tags:
                proxy_username = f"{username}-{'-'.join(tags)}"

        raw_proxy = f"{endpoint}:{proxy_username}:{password}" if preserve_raw else ""
        url_proxy = f"http://{proxy_username}:{password}@{endpoint}"
        logger.info("已启用 %s 动态住宅代理入口: %s，代理用户名: %s", provider, endpoint, proxy_username)
        return {
            "provider": provider,
            "endpoint": endpoint,
            "username": proxy_username,
            "password": password,
            "raw_proxy": raw_proxy,
            "url_proxy": url_proxy,
            "preserve_raw": preserve_raw,
        }

    def _build_ipfoxy_proxy(self):
        parsed = self._parse_ipfoxy_proxy()
        if not parsed:
            return self.static_proxy
        return parsed["raw_proxy"] if parsed["preserve_raw"] else parsed["url_proxy"]

    def get_browser_proxy_settings(self):
        proxy_url = self._build_ipfoxy_proxy()
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

        return {
            "server": proxy_url,
            "bypass": "localhost",
        }

    @staticmethod
    def is_raw_integrated_proxy(proxy_url: str) -> bool:
        return bool(proxy_url and "://" not in proxy_url and "@" not in proxy_url and proxy_url.count(":") >= 3)

    def rotate_if_needed(self):
        return self._build_ipfoxy_proxy()

    def check_health(self, timeout: int = 15) -> Dict[str, Any]:
        proxy_url = self._build_ipfoxy_proxy() or self.static_proxy
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
                proxy_handler = urllib.request.ProxyHandler({"https": proxy_url})
                opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPHandler)
                with opener.open("http://www.ip-api.com/json", timeout=timeout) as response:
                    payload = __import__("json").loads(response.read().decode("utf-8", errors="replace"))
            else:
                proxies = {"http": proxy_url, "https": proxy_url}
                response = requests.get("https://ipinfo.io/json", proxies=proxies, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
            result["connect_ok"] = True
            result["ok"] = True
            result["ip"] = str(payload.get("ip", "") or "")
            result["country"] = str(payload.get("country", "") or "")
            expected_country = ""
            sticky_session = ""
            if self.dynamic_proxy_config and self.dynamic_proxy_config.enabled:
                expected_country = str(self.dynamic_proxy_config.country or "").strip().upper()
                sticky_session = str(self.dynamic_proxy_config.session or "").strip()
            result["country_match"] = None if not expected_country else result["country"].upper() == expected_country
            result["sticky_session"] = None if not sticky_session else "sessid-" in proxy_url
            result["message"] = "代理连通正常"
            return result
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            result["message"] = f"代理请求失败，HTTP {status_code}"
            return result
        except requests.RequestException as exc:
            result["message"] = f"代理连通失败：{exc}"
            return result
