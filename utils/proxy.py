"""代理设置工具函数。"""

import os
from typing import Optional


def setup_proxy(http_proxy: Optional[str] = None) -> None:
    """设置HTTP代理。

    Args:
        http_proxy: 代理地址，如"http://127.0.0.1:7890"
    """
    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
        os.environ["HTTPS_PROXY"] = http_proxy


def clear_proxy() -> None:
    """清除HTTP代理设置。"""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"

