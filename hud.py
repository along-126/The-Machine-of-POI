"""Offline The Machine-inspired HUD. Seven styles; fifteen selectable captions."""
from __future__ import annotations

import cv2
import numpy as np

from classifications import category_for, WHITE

FONT = cv2.FONT_HERSHEY_SIMPLEX


def _line(canvas, start, end, color, thickness=2):
    cv2.line(canvas, tuple(map(int, start)), tuple(map(int, end)), color, thickness, cv2.LINE_AA)


def _dashed(canvas, start, end, color, dash=10, gap=8, thickness=2):
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    length = np.linalg.norm(end - start)
    if length < 1:
        return
    direction = (end - start) / length
    for p in np.arange(0, length, dash + gap):
        _line(canvas, start + direction*p, start + direction*min(p+dash, length), color, thickness)


def _draw_box(img, box, label, glow):
    h, w = img.shape[:2]
    x, y, bw, bh = map(float, box)
    pad = max(7, min(bw, bh) * .09)
    x1, y1 = max(4, round(x-pad)), max(40, round(y-pad))
    x2, y2 = min(w-5, round(x+bw+pad)), min(h-33, round(y+bh+pad))
    if x2-x1 < 18 or y2-y1 < 18:
        return

    style = category_for(label)
    accent = style.accents
    # The analog frame is predominantly black, but a charcoal contour keeps it
    # visible over footage at night; its corner/crosshair marks remain yellow.
    edge = (25, 25, 28) if style.key == "ANALOG" else style.edge
    corner = max(11, min(27, round(min(x2-x1, y2-y1)*.19)))
    cross = max(8, min(12, round(corner*.55)))

    if style.key == "ANALOG":
        # Black dashed perimeter with yellow corners and four yellow crosshairs.
        for a,b in [((x1,y1),(x2,y1)), ((x1,y2),(x2,y2)),
                    ((x1,y1),(x1,y2)), ((x2,y1),(x2,y2))]:
            _dashed(img, a, b, edge, thickness=3)
    else:
        for a,b in [((x1+corner,y1),(x2-corner,y1)), ((x1+corner,y2),(x2-corner,y2)),
                    ((x1,y1+corner),(x1,y2-corner)), ((x2,y1+corner),(x2,y2-corner))]:
            _dashed(img, a, b, edge)

    segments = [
        ((x1,y1),(x1+corner,y1)), ((x1,y1),(x1,y1+corner)),
        ((x2,y1),(x2-corner,y1)), ((x2,y1),(x2,y1+corner)),
        ((x1,y2),(x1+corner,y2)), ((x1,y2),(x1,y2-corner)),
        ((x2,y2),(x2-corner,y2)), ((x2,y2),(x2,y2-corner)),
    ]
    midx, midy = (x1+x2)//2, (y1+y2)//2
    segments += [
        ((midx,y1),(midx,y1+cross)), ((midx,y2),(midx,y2-cross)),
        ((x1,midy),(x1+cross,midy)), ((x2,midy),(x2-cross,midy)),
    ]
    for a,b in segments:
        _line(glow, a, b, accent, 7)
        _line(img, a, b, accent, 3)

    # Long multi-word captions auto-size to remain within the screen width.
    label = label if isinstance(label, str) else "IRRELEVANT"
    scale, thickness = .57, 2
    target_width = max(80, w-18)
    while scale > .32 and cv2.getTextSize(label, FONT, scale, thickness)[0][0] + 14 > target_width:
        scale -= .03
    (tw, th), baseline = cv2.getTextSize(label, FONT, scale, thickness)
    tx = max(4, min(x1, w-tw-17))
    ty = y2 + 6
    height = th + baseline + 13
    if ty + height > h-31:
        ty = max(41, y1-height-6)
    cv2.rectangle(img, (tx,ty), (tx+tw+13,ty+height), style.caption_bg, -1)
    # Hairline outline helps white or blue caption backgrounds on bright video.
    cv2.rectangle(img, (tx,ty), (tx+tw+13,ty+height), (48,51,59), 1)
    cv2.putText(img, label, (tx+6,ty+th+6), FONT, scale, style.caption_fg, thickness, cv2.LINE_AA)


def render(frame: np.ndarray, tracks: list, fps: float=0.0, source_mode: str="LOCAL") -> np.ndarray:
    """Draw detection boxes; source_mode only affects informational footer."""
    img = frame.copy()
    h, w = img.shape[:2]
    tint = np.zeros_like(img)
    tint[:] = (22,10,4)
    img = cv2.addWeighted(img, .87, tint, .13, 0)
    img[::5] = (img[::5].astype(np.float32)*.87).astype(np.uint8)
    glow = np.zeros_like(img)
    for track in tracks:
        _draw_box(img, track.box, track.label, glow)
    if tracks:
        halo = cv2.GaussianBlur(glow, (0,0), 5)
        img = cv2.add(img, (halo.astype(np.float32)*.5).astype(np.uint8))

    cv2.rectangle(img, (0,0), (w,39), (4,6,10), -1)
    cv2.putText(img, "THE MACHINE  /  FACE CLASSIFICATION", (14,25),FONT,.48,(230,235,250),1,cv2.LINE_AA)
    footer_source = "LOCAL // OFFLINE" if source_mode == "LOCAL" else "NETWORK // USER ENABLED"
    footer = f"{footer_source}  //  FACES: {len(tracks)}  //  {fps:.0f} FPS"
    cv2.rectangle(img, (0,h-30), (w,h), (4,6,10), -1)
    cv2.putText(img, footer, (13,h-10), FONT,.42,(210,211,216),1,cv2.LINE_AA)
    return img
