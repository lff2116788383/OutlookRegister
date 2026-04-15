from __future__ import annotations

import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

try:
    import requests
except ImportError:
    requests = None

# 运行模式：
# direct = 模式 2，直接使用「动态住宅代理 -> 独享端口」页面里的固定入口
# api    = 模式 1，通过 pickdynamicips API 先提取代理
PROXY_MODE = "api"

# 模式 2：把 Kookeey「独享端口」页面里的信息填在这里
DIRECT_PROXY_HOST = "res28.kookeey.info"
DIRECT_PROXY_PORT = 13115
DIRECT_PROXY_USERNAME = "bad5b75e"
DIRECT_PROXY_PASSWORD = "f54b85b6"

# 模式 1：按账号后台生成的动态住宅代理提取链接填写，保留备用
KOOKEEY_PICK_URL = (
    "https://www.kookeey.com/pickdynamicips"
    "?t=2&auth=pwd&format=4&n=1&p=http&gate=global&g=US&r=5&type=txt"
    "&sign=faeea843a7077b8d090b93fb15ea2171&accessid=4941943&upf=1,5&dl="
)

TEST_URLS = [
    "http://www.ip-api.com/json",
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
]


def read_url(url: str, timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_proxy(raw_proxy: str) -> str:
    raw_proxy = raw_proxy.strip()
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
        return build_proxy_url(host, port, username, password)

    return f"http://{raw_proxy}"


def build_proxy_url(host: str, port: int | str, username: str = "", password: str = "") -> str:
    host = str(host).strip()
    port = str(port).strip()
    username = str(username).strip()
    password = str(password).strip()

    if not host or not port:
        raise RuntimeError("独享端口的 host/port 不能为空")

    if username or password:
        return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"

    return f"http://{host}:{port}"


def pick_kookeey_proxy() -> tuple[str, str]:
    body = read_url(KOOKEEY_PICK_URL).strip()
    if not body:
        raise RuntimeError("Kookeey 提取接口返回为空")

    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if not first_line:
        raise RuntimeError(f"Kookeey 提取接口未返回有效代理：{body!r}")

    return first_line, normalize_proxy(first_line)


def get_proxy_by_mode() -> tuple[str, str]:
    mode = PROXY_MODE.strip().lower()
    if mode == "direct":
        proxy_url = build_proxy_url(
            DIRECT_PROXY_HOST,
            DIRECT_PROXY_PORT,
            DIRECT_PROXY_USERNAME,
            DIRECT_PROXY_PASSWORD,
        )
        return "Kookeey 独享端口", proxy_url

    if mode == "api":
        return pick_kookeey_proxy()

    raise RuntimeError(f"未知 PROXY_MODE: {PROXY_MODE!r}，只能是 direct 或 api")


def split_proxy_endpoint(proxy_url: str) -> tuple[str, int]:
    split = urlsplit(proxy_url)
    host = split.hostname or ""
    port = split.port or 0
    if not host or not port:
        raise RuntimeError(f"无法解析代理地址: {proxy_url}")
    return host, port


def probe_proxy_gateway(proxy_url: str, timeout: int = 10) -> None:
    host, port = split_proxy_endpoint(proxy_url)
    with socket.create_connection((host, port), timeout=timeout):
        return None


def resolve_host_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise RuntimeError(f"DNS 解析失败: {exc}") from exc

    ips: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in ips:
            ips.append(ip)
    return ips


def probe_ip_list(ips: list[str], port: int, timeout: int = 5) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for ip in ips:
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                results.append((ip, True, "ok"))
        except Exception as exc:
            results.append((ip, False, str(exc)))
    return results



def mask_proxy(proxy_url: str) -> str:
    split = urlsplit(proxy_url)
    if not split.scheme:
        return proxy_url

    username = split.username or ""
    if len(username) > 8:
        username = f"{username[:6]}...{username[-2:]}"

    auth = ""
    if username:
        auth = username
        if split.password:
            auth += ":***"
        auth += "@"

    host = split.hostname or ""
    port = f":{split.port}" if split.port else ""
    return f"{split.scheme}://{auth}{host}{port}"


def read_url_with_urllib(url: str, proxy_url: str, timeout: int = 30) -> str:

    proxy_handler = urllib.request.ProxyHandler({
        "http": proxy_url,
        "https": proxy_url,
    })
    opener = urllib.request.build_opener(proxy_handler)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def read_url_with_requests(url: str, proxy_url: str, timeout: int = 30) -> str:

    if requests is None:
        raise RuntimeError("当前环境未安装 requests，跳过 requests 复核")

    response = requests.get(
        url,
        proxies={"http": proxy_url, "https": proxy_url},
        timeout=timeout,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    response.raise_for_status()
    return response.text


def test_kookeey_dynamic_proxy() -> int:
    print(f"[1/3] 当前代理模式: {PROXY_MODE}")

    try:
        raw_proxy, proxy_url = get_proxy_by_mode()
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        print(f"获取代理失败: {exc}")
        return 1

    print(f"代理来源/原始值: {raw_proxy}")
    print(f"标准代理 URL: {mask_proxy(proxy_url)}")

    try:
        host, port = split_proxy_endpoint(proxy_url)
    except Exception as exc:
        print(f"解析代理地址失败: {exc}")
        return 1

    print("\n[2/4] 正在进行 DNS 解析...")
    try:
        ips = resolve_host_ips(host, port)
        print(f"DNS 解析结果 ({len(ips)} 个):")
        for ip in ips:
            print(f"- {ip}")
    except Exception as exc:
        print(f"DNS 解析失败: {exc}")
        return 1

    print("\n[3/4] 正在逐个 IP 探测端口连通性...")
    probe_results = probe_ip_list(ips, port)
    for ip, ok, detail in probe_results:
        status = "可达" if ok else "不可达"
        print(f"- {ip}:{port} -> {status} ({detail})")

    print("\n[4/4] 正在探测代理网关是否可达...")
    try:
        probe_proxy_gateway(proxy_url)
        print(f"代理网关可达: {host}:{port}")
    except Exception as exc:
        print(f"代理网关不可达: {exc}")
        print("这说明本机到代理服务器的 TCP 连接建立失败，优先检查 host、端口、账号状态、VPN 或本机网络。")
        return 1

    print("\n[5/5] 正在使用该代理访问测试接口...")

    ok_count = 0
    for url in TEST_URLS:
        print(f"\n测试地址: {url}")
        passed = False

        try:
            body = read_url_with_urllib(url, proxy_url)
            print("urllib 测试成功，返回内容:")
            print(body[:1000])
            passed = True
        except Exception as exc:
            print(f"urllib 测试失败: {exc}")

        if requests is not None:
            try:
                body = read_url_with_requests(url, proxy_url)
                print("requests 测试成功，返回内容:")
                print(body[:1000])
                passed = True
            except Exception as exc:
                print(f"requests 测试失败: {exc}")
        else:
            print("requests 未安装，已跳过 requests 复核")

        if passed:
            ok_count += 1

    if ok_count == 0:
        print("\n所有测试地址均失败；若第 [2/3] 步已通过，则更可能是代理认证、协议或目标站点限制问题。")
        return 1

    print(f"\n代理测试完成，成功 {ok_count}/{len(TEST_URLS)} 个测试地址。")
    return 0


if __name__ == "__main__":
    sys.exit(test_kookeey_dynamic_proxy())
