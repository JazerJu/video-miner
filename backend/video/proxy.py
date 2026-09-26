"""
统一代理配置工具。

所有需要出网代理的功能（yt-dlp 下载、LLM 调用等）都通过此模块获取代理地址。

优先级：用户配置的 proxy_url > Docker 环境变量 HTTPS_PROXY > 直连

使用方式：
    from video.proxy import get_effective_proxy

    proxy = get_effective_proxy(use_proxy=True)
    if proxy:
        # 使用代理
    else:
        # 直连
"""

import os
from typing import Optional


def get_effective_proxy(use_proxy: bool) -> Optional[str]:
    """
    根据功能开关获取代理 URL。

    Args:
        use_proxy: 该功能是否启用代理

    Returns:
        str: 代理 URL（如 "http://host:7890"）
        None: 不使用代理
    """
    if not use_proxy:
        return None

    # 优先级 1：用户在前端设置的代理地址
    from video.views.set_setting import load_all_settings

    settings = load_all_settings()
    proxy = settings.get("Media Credentials", {}).get("proxy_url", "").strip()
    if proxy:
        return proxy

    # 优先级 2：Docker 环境变量
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
        or None
    )


_USABLE_SOCKS = ("socks4", "socks4a", "socks5", "socks5h")


def sanitize_proxy_env() -> str:
    """Drop ALL_PROXY when nothing here can use it. Returns a message, or "" when nothing changed.

    Desktop proxy tools export ALL_PROXY=socks://127.0.0.1:port. "socks" is not a scheme any
    client accepts: yt-dlp raises "Unknown SOCKS proxy version: socks" and requests raises
    "Missing dependencies for SOCKS support" unless PySocks is installed. HTTP_PROXY and
    HTTPS_PROXY point at the same port and work, so the variable is only removed.
    """
    dropped = []
    for key in ("ALL_PROXY", "all_proxy"):
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        scheme = value.split("://", 1)[0].lower()
        if scheme in ("http", "https"):
            continue
        if scheme in _USABLE_SOCKS:
            try:
                import socks  # noqa: F401  (PySocks, needed by requests for socks proxies)
                continue
            except ImportError:
                pass
        del os.environ[key]
        dropped.append(f"{key}={scheme}://...")
    return ("忽略无法使用的代理环境变量：" + ", ".join(dropped)) if dropped else ""
