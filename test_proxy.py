# from __future__ import annotations

# import json
# import os
# import sys
# import urllib.request
# from pathlib import Path
# from urllib.parse import urlsplit

# import requests

# from app_config import AppConfig, CONFIG_PATH
# from services import ProxyManager


# def mask_proxy(proxy_url: str) -> str:
#     split = urlsplit(proxy_url)
#     if split.scheme:
#         host = split.hostname or ""
#         port = split.port or ""
#         username = split.username or ""
#         if len(username) > 8:
#             username = f"{username[:6]}...{username[-2:]}"
#         password_mask = "***" if split.password else ""
#         auth = ""
#         if username:
#             auth = username
#             if password_mask:
#                 auth += f":{password_mask}"
#             auth += "@"
#         return f"{split.scheme}://{auth}{host}:{port}"

#     parts = proxy_url.split(":")
#     if len(parts) >= 4:
#         host = parts[0]
#         port = parts[1]
#         username = parts[2]
#         if len(username) > 8:
#             username = f"{username[:6]}...{username[-2:]}"
#         return f"{host}:{port}:{username}:***"

#     return proxy_url


# def get_raw_integrated_proxy(config: AppConfig) -> str:
#     dynamic_proxy = config.oauth2.dynamic_residential_proxy
#     endpoint = dynamic_proxy.endpoint.strip()
#     if dynamic_proxy.enabled and not dynamic_proxy.username.strip() and not dynamic_proxy.password.strip():
#         if "@" not in endpoint and endpoint.count(":") >= 3:
#             return endpoint
#     return ""


# def open_url_without_system_proxy(url: str, timeout: int = 20) -> str:
#     opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
#     with opener.open(url, timeout=timeout) as response:
#         return response.read().decode("utf-8", errors="replace")


# def open_url_with_raw_proxy_http(proxy_url: str, url: str, timeout: int = 20) -> str:
#     opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
#     with opener.open(url, timeout=timeout) as response:
#         return response.read().decode("utf-8", errors="replace")


# def open_url_with_raw_proxy_https_key_only(proxy_url: str, url: str, timeout: int = 20) -> str:
#     opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy_url}))
#     with opener.open(url, timeout=timeout) as response:
#         return response.read().decode("utf-8", errors="replace")


# def try_fetch(label: str, fetcher) -> None:
#     print(f"\n[{label}]")
#     try:
#         body = fetcher()
#         print(body[:800])
#     except Exception as exc:
#         print(f"异常: {exc}")


# def test_proxy(config_path: Path) -> int:
#     config = AppConfig.load(config_path)
#     dynamic_proxy = config.oauth2.dynamic_residential_proxy
#     raw_integrated_proxy = get_raw_integrated_proxy(config)
#     manager = ProxyManager(static_proxy=config.proxy.url, dynamic_proxy_config=dynamic_proxy)
#     proxy_url = raw_integrated_proxy or manager.rotate_if_needed() or config.proxy.url

#     print(f"配置文件: {config_path}")
#     print(f"动态代理启用: {dynamic_proxy.enabled}")
#     print(f"静态代理: {config.proxy.url or '-'}")
#     print(f"最终代理: {mask_proxy(proxy_url) if proxy_url else '-'}")
#     print(f"代理格式: {'IPFoxy 一体化原始格式' if raw_integrated_proxy else '标准代理 URL 格式'}")
#     print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY') or '-'}")
#     print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY') or '-'}")

#     if not proxy_url:
#         print("未配置可用代理")
#         return 1

#     http_test_url = "http://www.ip-api.com/json"
#     https_test_urls = [
#         "https://ipinfo.io/json",
#         "https://api.ipify.org?format=json",
#     ]

#     try_fetch("直连且禁用系统代理 -> ip-api", lambda: open_url_without_system_proxy(http_test_url))

#     if raw_integrated_proxy:
#         try_fetch(
#             "IPFoxy 原始串一体化，仅配 https 键 -> ip-api",
#             lambda: open_url_with_raw_proxy_https_key_only(proxy_url, http_test_url),
#         )
#         try_fetch(
#             "IPFoxy 原始串一体化，同时配 http/https 键 -> ip-api",
#             lambda: open_url_with_raw_proxy_http(proxy_url, http_test_url),
#         )

#         for url in https_test_urls:
#             try_fetch(
#                 f"IPFoxy 原始串一体化，同时配 http/https 键 -> {url}",
#                 lambda current_url=url: open_url_with_raw_proxy_http(proxy_url, current_url),
#             )
#         return 0

#     proxies = {"http": proxy_url, "https": proxy_url}
#     for url in [http_test_url, *https_test_urls]:
#         print(f"\n[requests 标准代理 -> {url}]")
#         try:
#             response = requests.get(url, proxies=proxies, timeout=20)
#             print(f"HTTP 状态: {response.status_code}")
#             print(response.text[:800])
#         except Exception as exc:
#             print(f"异常: {exc}")

#     return 0


# if __name__ == "__main__":
#     path = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_PATH
#     raise SystemExit(test_proxy(path))


import urllib.request

if __name__ == '__main__':
    proxy = urllib.request.ProxyHandler({
        'https': 'customer-UcmKU4timu-cc-US-st-NewYork-city-NewYork-sessid-1776245039_10000:hFts6JwqRel2bL1@gate-us.ipfoxy.io:58688',
        'http': 'customer-UcmKU4timu-cc-US-st-NewYork-city-NewYork-sessid-1776245039_10000:hFts6JwqRel2bL1@gate-us.ipfoxy.io:58688',
    })
    opener = urllib.request.build_opener(proxy, urllib.request.HTTPHandler)
    urllib.request.install_opener(opener)
    content = urllib.request.urlopen('http://www.ip-api.com/json').read()
    print(content)