"""The Machine-inspired HUD: square frame, restrained glow, condensed labels.

On Windows, the user's installed Bahnschrift font is used; no font is copied or
redistributed. Pillow is optional for direct users of render(); cv2 remains a fallback.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np

from classifications import category_for

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Defensive fallback for older installations.
    Image = ImageDraw = ImageFont = None

FONT = cv2.FONT_HERSHEY_DUPLEX


def _line(canvas, start, end, color, thickness=2):
    cv2.line(canvas, tuple(map(int, start)), tuple(map(int, end)), color, thickness, cv2.LINE_AA)


def _dashed(canvas, start, end, color, dash=10, gap=8, thickness=2):
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    length = np.linalg.norm(end-start)
    if length < 1:
        return
    direction = (end-start)/length
    for p in np.arange(0, length, dash+gap):
        _line(canvas, start+direction*p, start+direction*min(p+dash,length), color, thickness)


def square_rect(box, image_width: int, image_height: int):
    """A tracked rectangle becomes a *square* enclosing the face, screen-clamped.

    The top and bottom of the video are reserved for source banners.
    """
    x,y,bw,bh = map(float,box)
    pad = max(7., min(bw,bh)*.09)
    low_y, high_y = 41, max(60, image_height-34)
    avail = max(18., min(image_width-10, high_y-low_y))
    side = min(avail, max(bw,bh)+2*pad)
    side = max(18., side)
    cx,cy = x+bw/2,y+bh/2
    x1 = max(5., min(cx-side/2, image_width-5-side))
    y1 = max(float(low_y), min(cy-side/2, high_y-side))
    # Use the same rounded side so pixel widths and heights match exactly.
    side_i = max(18, int(round(side)))
    xi,yi = int(round(x1)),int(round(y1))
    return xi,yi,xi+side_i,yi+side_i


@lru_cache(maxsize=16)
def _label_patch(label: str, category_key: str, font_size: int = 25):
    """Build a BGR text patch once; no PIL conversion of the full video frame."""
    style=category_for(label)
    if ImageFont is None:
        return None
    files = [
        Path('C:/Windows/Fonts/bahnschrift.ttf'),
        Path('C:/Windows/Fonts/arialnb.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'),
    ]
    font=None
    for path in files:
        try:
            if path.is_file():
                font=ImageFont.truetype(str(path), font_size)
                break
        except OSError:
            pass
    if font is None:
        font=ImageFont.load_default()
    box=font.getbbox(label)
    text_width=max(1,box[2]-box[0])
    text_height=max(1,box[3]-box[1])
    im=Image.new('RGB',(text_width+18, text_height+14),tuple(reversed(style.caption_bg)))
    draw=ImageDraw.Draw(im)
    draw.text((9-box[0],7-box[1]),label,font=font,fill=tuple(reversed(style.caption_fg)))
    return cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2BGR)


def _draw_label(img, label, x1,y1,x2,y2,style):
    h,w=img.shape[:2]
    label=label if isinstance(label,str) else 'IRRELEVANT'
    patch=_label_patch(label,style.key)
    if patch is not None:
        ph,pw=patch.shape[:2]
        # Prefer the original series' right-of-frame ID tag; move beneath the
        # square when the label won't fit on the right.
        if x2+9+pw <= w-4:
            tx,ty=x2+9,max(42,min((y1+y2-ph)//2,h-ph-31))
        else:
            tx,ty=max(4,min(x1,w-pw-4)),min(h-ph-31,y2+6)
            if ty < 40: ty=max(40,y1-ph-5)
        pw=min(pw,w-tx)
        ph=min(ph,h-ty)
        if pw>0 and ph>0:
            img[ty:ty+ph,tx:tx+pw]=patch[:ph,:pw]
        return
    scale=.54
    (tw,th),base=cv2.getTextSize(label,FONT,scale,1)
    tx=x2+8 if x2+tw+22<=w else max(4,min(x1,w-tw-15))
    ty=min(y2+6,h-th-base-22)
    cv2.rectangle(img,(tx,ty),(min(w-1,tx+tw+13),ty+th+base+12),style.caption_bg,-1)
    cv2.putText(img,label,(tx+6,ty+th+5),FONT,scale,style.caption_fg,1,cv2.LINE_AA)


def _draw_box(img, box, label, glow):
    h,w=img.shape[:2]
    x1,y1,x2,y2=square_rect(box,w,h)
    if x2-x1<18: return
    style=category_for(label)
    edge=(25,25,28) if style.key=='ANALOG' else style.edge
    accent=style.accents
    corner=max(11,min(27,round((x2-x1)*.19)))
    cross=max(8,min(12,round(corner*.55)))
    for a,b in [((x1+corner,y1),(x2-corner,y1)),((x1+corner,y2),(x2-corner,y2)),
                ((x1,y1+corner),(x1,y2-corner)),((x2,y1+corner),(x2,y2-corner))]:
        _dashed(img,a,b,edge,dash=9,gap=10,thickness=2)
    segments=[
        ((x1,y1),(x1+corner,y1)),((x1,y1),(x1,y1+corner)),
        ((x2,y1),(x2-corner,y1)),((x2,y1),(x2,y1+corner)),
        ((x1,y2),(x1+corner,y2)),((x1,y2),(x1,y2-corner)),
        ((x2,y2),(x2-corner,y2)),((x2,y2),(x2,y2-corner)),
    ]
    mx,my=(x1+x2)//2,(y1+y2)//2
    segments.extend([
        ((mx,y1),(mx,y1+cross)),((mx,y2),(mx,y2-cross)),
        ((x1,my),(x1+cross,my)),((x2,my),(x2-cross,my)),
    ])
    for a,b in segments:
        _line(glow,a,b,accent,4)
        _line(img,a,b,accent,2)
    _draw_label(img,label,x1,y1,x2,y2,style)


def render(frame: np.ndarray,tracks: list,fps: float=0.0,source_mode: str='LOCAL')->np.ndarray:
    img=frame.copy()
    h,w=img.shape[:2]
    tint=np.zeros_like(img)
    tint[:]=(22,10,4)
    img=cv2.addWeighted(img,.90,tint,.10,0)
    img[::5]=(img[::5].astype(np.float32)*.92).astype(np.uint8)
    glow=np.zeros_like(img)
    for track in tracks:
        _draw_box(img,track.box,track.label,glow)
    if tracks:
        halo=cv2.GaussianBlur(glow,(0,0),3)
        img=cv2.add(img,(halo.astype(np.float32)*.16).astype(np.uint8))
    cv2.rectangle(img,(0,0),(w,39),(4,6,10),-1)
    cv2.putText(img,'THE MACHINE  /  FACE CLASSIFICATION',
                (14,25),FONT,.48,(230,235,250),1,cv2.LINE_AA)
    source='LOCAL // OFFLINE' if source_mode=='LOCAL' else 'NETWORK // USER ENABLED'
    footer=f'{source}  //  FACES: {len(tracks)}  //  {fps:.0f} FPS'
    cv2.rectangle(img,(0,h-30),(w,h),(4,6,10),-1)
    cv2.putText(img,footer,(13,h-10),FONT,.42,(210,211,216),1,cv2.LINE_AA)
    return img
