"""HTTP MJPEG reader for The Machine, independent of OpenCV's FFmpeg backend.

Works with authorized multipart/x-mixed-replace camera streams, including the
local test stream at http://127.0.0.1:8765/stream.mjpg.

It intentionally doesn't scrape video from websites or bypass access controls.
"""
from __future__ import annotations

import socket
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener, urlopen

import cv2
import numpy as np

MAX_BUFFER = 12 * 1024 * 1024


class MJPEGStreamError(RuntimeError):
    pass


class MjpegCapture:
    """Small cv2.VideoCapture-compatible reader for HTTP multipart MJPEG.

    Provides isOpened/read/release/set, the only methods used by main.py.
    HTTP and JPEG decoding happen on-device; no third-party service is involved.
    """

    def __init__(self, url: str, *, timeout: float = 8):
        self._response = None
        self._buffer = bytearray()
        self._first_frame = None
        self._opened = False
        self._last_error = ""
        self.url = url

        # Browsers may bypass corporate proxies for 127.0.0.1. Force direct
        # loopback access so the Python reader behaves the same way.
        host = (urlsplit(url).hostname or "").lower()
        opener = build_opener(ProxyHandler({})) if host in {"127.0.0.1", "localhost", "::1"} else None
        request = Request(url, headers={
            "Accept": "multipart/x-mixed-replace, image/jpeg, */*",
            "User-Agent": "THE-MACHINE/1.0",
            "Cache-Control": "no-cache",
        })
        try:
            self._response = (opener.open(request, timeout=timeout)
                              if opener is not None else urlopen(request, timeout=timeout))
            content_type = self._response.headers.get("Content-Type", "").lower()
            if "multipart/" not in content_type and "image/jpeg" not in content_type:
                raise MJPEGStreamError(
                    f"服务器返回了 {content_type or '未知内容类型'}，不是 MJPEG 视频流。"
                    "请确认填写的是 /stream.mjpg 等直接视频流地址，而非网页地址。"
                )
            self._first_frame = self._next_frame()
            if self._first_frame is None:
                raise MJPEGStreamError("已建立 HTTP 连接，但没有收到有效的 JPEG 视频画面。")
            self._opened = True
        except Exception as exc:
            self.release()
            if isinstance(exc, MJPEGStreamError):
                raise
            raise MJPEGStreamError(f"无法读取 MJPEG 视频流：{type(exc).__name__}: {exc}") from exc

    def isOpened(self) -> bool:
        return self._opened

    def set(self, _property_id, _value) -> bool:
        # A network stream's dimensions and buffers are server-controlled.
        return False

    def _next_frame(self):
        if self._response is None:
            return None
        while True:
            start = self._buffer.find(b"\xff\xd8")
            if start >= 0:
                end = self._buffer.find(b"\xff\xd9", start + 2)
                if end >= 0:
                    jpeg = bytes(self._buffer[start:end + 2])
                    del self._buffer[:end + 2]
                    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if image is not None:
                        return image
                    continue
                if start > 0:
                    del self._buffer[:start]
            elif len(self._buffer) > 3:
                # Preserve the last two bytes in case a JPEG marker crosses
                # the next network read boundary.
                del self._buffer[:-2]

            if len(self._buffer) > MAX_BUFFER:
                raise MJPEGStreamError("单帧视频数据超过安全大小上限（12MB）。")
            chunk = self._response.read(4096)
            if not chunk:
                return None
            self._buffer.extend(chunk)

    def read(self):
        if not self._opened:
            return False, None
        if self._first_frame is not None:
            result, self._first_frame = self._first_frame, None
            return True, result
        try:
            image = self._next_frame()
            if image is None:
                self._last_error = "视频流已经结束。"
                return False, None
            return True, image
        except (OSError, TimeoutError, socket.timeout, MJPEGStreamError) as exc:
            self._last_error = str(exc)
            return False, None

    @property
    def last_error(self):
        return self._last_error

    def release(self):
        self._opened = False
        if self._response is not None:
            try:
                self._response.close()
            except OSError:
                pass
            self._response = None
        self._first_frame = None
        self._buffer.clear()


def prefers_http_mjpeg(url: str) -> bool:
    """Recognize plain HTTP MJPEG camera endpoints before using FFmpeg."""
    info = urlsplit(url)
    if info.scheme.lower() not in ("http", "https"):
        return False
    path = info.path.lower()
    return any(token in path for token in (".mjpg", ".mjpeg", "/mjpg/", "/mjpeg/"))
