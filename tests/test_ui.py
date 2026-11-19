"""New HUD/boot visuals tests; no camera or Qt display required."""
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hud import square_rect, render
from standby import render_standby


def test_square_faces_stay_square_and_inside_image():
    for box in ([180, 100, 75, 140], [5, 10, 130, 60],
                [520, 440, 150, 170], [120, 100, 220, 220]):
        left, top, right, bottom = square_rect(box, 800, 600)
        assert right-left == bottom-top
        assert 0 <= left < right <= 800
        assert 0 <= top < bottom <= 600


def test_self_generated_intro_changes_over_time():
    one = render_standby(0.5, 640, 360)
    two = render_standby(1.5, 640, 360)
    assert one.shape == two.shape == (360, 640, 3)
    assert np.count_nonzero(one != two) > 500


def test_long_hud_label_fits_and_renders():
    blank = np.zeros((560, 900, 3), dtype=np.uint8)
    class Track:
        box=[550, 120, 150, 190]
        label='SECONDARY ASSET'
    result=render(blank, [Track()], 30)
    assert result.shape == blank.shape
    assert result.sum() > 0
