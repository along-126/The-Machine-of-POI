"""Offline tests: local files and adapter behavior, no camera or web required."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np
import pytest

from video_sources import (SourceOpenError, VideoSourceSpec,
                           VideoCaptureSession, open_video_source)


def test_open_local_video_and_end_of_file():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "test.avi"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"),
                                 10.0, (128, 96))
        assert writer.isOpened(), "Test OpenCV installation needs MJPEG AVI encoder"
        try:
            for index in range(4):
                frame = np.full((96, 128, 3), index * 30, dtype=np.uint8)
                writer.write(frame)
        finally:
            writer.release()

        spec = VideoSourceSpec("file", str(path), "file:test", "测试视频")
        cap = open_video_source(spec)
        try:
            assert cap.isOpened()
            assert cap.get(cv2.CAP_PROP_FPS) > 0
            frames = []
            for _ in range(4):
                ok, frame = cap.read()
                assert ok and frame.shape == (96, 128, 3)
                frames.append(frame.mean())
            assert frames[-1] > frames[0]
            ok, _ = cap.read()
            assert not ok  # EOF, not a network failure
            assert cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            assert ok and frame is not None
        finally:
            cap.release()


def test_reject_missing_or_unsupported_file():
    with tempfile.TemporaryDirectory() as folder:
        for name in ("not_there.mp4", "notes.txt"):
            spec = VideoSourceSpec("file", str(Path(folder) / name), "a", "a")
            with pytest.raises(SourceOpenError):
                open_video_source(spec)


def test_network_rejects_embedded_credentials_without_connecting():
    spec = VideoSourceSpec("network", "rtsp://test:secret@example.test/live", "n", "n")
    with pytest.raises(SourceOpenError):
        open_video_source(spec)


def test_unknown_kind_is_rejected():
    with pytest.raises(SourceOpenError, match="未知视频源类型"):
        open_video_source(VideoSourceSpec("other", "test", "x", "x"))


def test_source_spec_does_not_assume_a_fixed_tile_count():
    sources = [VideoSourceSpec("file", f"video-{i}.mp4", str(i), f"Camera {i}")
               for i in range(32)]
    assert len(set(x.key for x in sources)) == 32
