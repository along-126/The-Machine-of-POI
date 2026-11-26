"""Extensible, single-source video adapters for The Machine.

This module deliberately does not own the UI or face detection. Every source
provides the same capture-like API, making it reusable by future multi-tile UI.
Opening any remote source must only follow an explicit user action.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import cv2

from camera_sources import validate_stream_url
from mjpeg_capture import MjpegCapture, MJPEGStreamError, prefers_http_mjpeg

SUPPORTED_FILE_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm"})


class SourceOpenError(RuntimeError):
    """A selected source could not be opened or decoded."""


@dataclass(frozen=True)
class VideoSourceSpec:
    """One source definition; more sources can be added without a fixed limit."""

    kind: str  # local | file | network
    target: int | str
    key: str
    display_name: str


class VideoCaptureSession:
    """Uniform wrapper around cv2.VideoCapture and HTTP/MJPEG adapters."""

    def __init__(self, spec: VideoSourceSpec, capture: Any):
        self.spec = spec
        self._capture = capture
    @property
    def last_error(self) -> str:
        return str(getattr(self._capture, "last_error", ""))

    def read(self):
        return self._capture.read()

    def release(self):
        self._capture.release()

    def isOpened(self):
        return self._capture.isOpened()

    def set(self, prop: int, value: float) -> bool:
        setter = getattr(self._capture, "set", None)
        return bool(setter(prop, value)) if callable(setter) else False

    def get(self, prop: int) -> float:
        getter = getattr(self._capture, "get", None)
        return float(getter(prop)) if callable(getter) else 0.0


def _opened_capture(cap: Any, spec: VideoSourceSpec) -> VideoCaptureSession:
    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        raise SourceOpenError("无法打开视频源；请检查设备、文件编码或网络地址。")
    return VideoCaptureSession(spec, cap)


def open_video_source(spec: VideoSourceSpec) -> VideoCaptureSession:
    """Open one explicitly selected source without modifying other sessions.

    Future 4/8/16-tile layouts can instantiate independent sessions from a
    list of VideoSourceSpec objects; no tile-count assumptions are made here.
    """
    if spec.kind == "local":
        index = int(spec.target)
        if index < 0:
            raise SourceOpenError("摄像头编号不能为负数。")
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(index)
        return _opened_capture(cap, spec)

    if spec.kind == "file":
        path = Path(str(spec.target)).expanduser()
        if path.suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
            raise SourceOpenError("不支持该视频格式。请使用 MP4、AVI、MKV、MOV、M4V 或 WEBM 文件。")
        if not path.is_file():
            raise SourceOpenError("找不到本地视频文件，请检查文件路径。")
        return _opened_capture(cv2.VideoCapture(str(path)), spec)

    if spec.kind == "network":
        try:
            url = validate_stream_url(str(spec.target))
        except ValueError as exc:
            raise SourceOpenError(str(exc)) from exc
        if prefers_http_mjpeg(url):
            try:
                return _opened_capture(MjpegCapture(url, timeout=8), spec)
            except MJPEGStreamError as exc:
                raise SourceOpenError(f"HTTP/MJPEG 连接失败：{exc}") from exc
        try:
            cap = cv2.VideoCapture(
                url, cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
                 cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000],
            )
        except (TypeError, cv2.error):
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened() and url.lower().startswith(("http://", "https://")):
            cap.release()
            try:
                cap = MjpegCapture(url, timeout=8)
            except MJPEGStreamError as exc:
                raise SourceOpenError(f"FFmpeg 和 HTTP/MJPEG 均无法读取该地址：{exc}") from exc
        return _opened_capture(cap, spec)

    raise SourceOpenError(f"未知视频源类型：{spec.kind}")
