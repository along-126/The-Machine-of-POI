"""UI-only math helpers, independent of Qt and the face-recognition pipeline."""

from __future__ import annotations

import math


def smooth_pulse_opacity(elapsed: float, period: float = 2.1) -> float:
    """Smooth, periodic fade 0→1→0 (no abrupt visibility toggles)."""
    if period <= 0:
        return 1.0
    return max(0.0, min(1.0, 0.5 - 0.5 * math.cos(
        2.0 * math.pi * max(0.0, elapsed) / period
    )))
