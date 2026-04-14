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
