"""Original animated boot-loop imagery; no television footage or audio is bundled."""
from __future__ import annotations

import math
import cv2
import numpy as np


def render_standby(seconds: float, width: int = 960, height: int = 540) -> np.ndarray:
    """Return a self-generated monochrome surveillance-style frame (BGR)."""
    width, height = max(160, int(width)), max(120, int(height))
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (12, 10, 9)
    # Subtle drifting monochrome monitor background, not footage from any show.
    x = np.arange(width, dtype=np.float32)
    band = 11 + 8 * np.sin(x / 72.0 + seconds * 0.37)
    frame[:, :, 0] += band.astype(np.uint8)[None, :]
    frame[:, :, 1] += (band * .66).astype(np.uint8)[None, :]
    frame[:, :, 2] += (band * .45).astype(np.uint8)[None, :]
    grid = (41, 42, 44)
    for gx in range(0, width, max(48, width // 13)):
        cv2.line(frame, (gx, 0), (gx, height), grid, 1, cv2.LINE_AA)
    for gy in range(0, height, max(45, height // 9)):
        cv2.line(frame, (0, gy), (width, gy), grid, 1, cv2.LINE_AA)

    # Slowly moving generic blocks and target reticles.
    cx = int(width * (.49 + .08 * math.sin(seconds * .26)))
    cy = int(height * (.51 + .07 * math.cos(seconds * .31)))
    box = max(70, int(min(width, height) * .34))
    half = box // 2
    x1, y1, x2, y2 = cx - half, cy - half, cx + half, cy + half
    color = (126, 142, 149)
    for a,b in [((x1,y1),(x1+20,y1)),((x1,y1),(x1,y1+20)),
                ((x2,y1),(x2-20,y1)),((x2,y1),(x2,y1+20)),
                ((x1,y2),(x1+20,y2)),((x1,y2),(x1,y2-20)),
                ((x2,y2),(x2-20,y2)),((x2,y2),(x2,y2-20))]:
        cv2.line(frame, a, b, color, 2, cv2.LINE_AA)
    cv2.line(frame, (cx - 11, cy), (cx+11, cy), color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx,cy-11),(cx,cy+11),color,1,cv2.LINE_AA)
    line_y = int((seconds * 105) % height)
    cv2.line(frame,(0,line_y),(width,line_y),(68,76,84),1,cv2.LINE_AA)
    frame[::4] = (frame[::4] * .80).astype(np.uint8)
    cv2.putText(frame, 'THE MACHINE // SYSTEM INITIALIZING',
                (22,37),cv2.FONT_HERSHEY_DUPLEX,.55,(184,194,203),1,cv2.LINE_AA)
    cv2.putText(frame, 'LOCAL / SIMULATED SURVEILLANCE VISUAL',
                (22,height-25),cv2.FONT_HERSHEY_SIMPLEX,.42,(135,145,153),1,cv2.LINE_AA)
    cv2.putText(frame, f'{int(seconds*24)%100000:05d}  //  CHANNEL 01',
                (max(22,width-280),height-25),cv2.FONT_HERSHEY_SIMPLEX,.42,(135,145,153),1,cv2.LINE_AA)
    return frame
