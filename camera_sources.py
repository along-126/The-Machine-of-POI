"""Helpers for user-authorized video streams, never for website scraping."""
from __future__ import annotations
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"rtsp", "rtsps", "http", "https"})


def validate_stream_url(url: str) -> str:
    """Allow direct stream URLs only; reject URLs with embedded credentials.

    Access is explicitly initiated by the user; no source is polled on startup.
    """
    url = url.strip()
    if any(char in url for char in "\r\n\t") or not url or len(url) > 2048:
        raise ValueError("请输入有效的 RTSP / HTTP(S) 视频流地址。")
    try:
        info = urlsplit(url)
        if info.scheme.lower() not in ALLOWED_SCHEMES or not info.hostname:
            raise ValueError("仅支持 RTSP、RTSPS、HTTP、HTTPS 的直接视频流地址。")
        _ = info.port  # Triggers ValueError for malformed ports.
        if info.username is not None or info.password is not None:
            raise ValueError("为保护密码，请不要在地址中嵌入账号或密码。")
    except ValueError as exc:
        raise ValueError(f"视频地址无效：{exc}") from exc
    return url
