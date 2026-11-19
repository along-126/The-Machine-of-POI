"""No GUI is needed to verify timing of the READY/prompt fade."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui_effects import smooth_pulse_opacity


def test_pulse_is_smooth_and_periodic():
    assert smooth_pulse_opacity(0) == 0.0
    assert abs(smooth_pulse_opacity(1.05) - 1.0) < 1e-10
    assert abs(smooth_pulse_opacity(2.1)) < 1e-10
    assert abs(smooth_pulse_opacity(4.2)) < 1e-10
    assert abs(smooth_pulse_opacity(0.1) - smooth_pulse_opacity(0.1001)) < 0.001


def test_pulse_in_range():
    for i in range(300):
        value = smooth_pulse_opacity(i / 100)
        assert 0 <= value <= 1
