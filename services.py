from __future__ import annotations
import time
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
    def __init__(self, static_proxy=None, rotation_url=None):
        self.static_proxy = static_proxy
        self.rotation_url = rotation_url
        self.current_proxy = static_proxy

    def rotate_if_needed(self):
        if not self.rotation_url:
            return self.static_proxy
            
        try:
            logger.info("Requesting proxy rotation...")
            res = requests.get(self.rotation_url, timeout=30)
            if res.status_code == 200:
                # Assuming rotation URL returns the new proxy string or just triggers rotation
                # If it returns new proxy: self.current_proxy = res.text.strip()
                logger.info("Proxy rotated successfully")
                return self.current_proxy
        except Exception as e:
            logger.error(f"Proxy rotation failed: {e}")
        return self.current_proxy
