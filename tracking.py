"""Simple box smoothing and ID association for the visual HUD.

This is not an identity-verification security control.
"""
from dataclasses import dataclass
import numpy as np


def intersection_over_union(a, b):
    ax, ay, aw, ah = [float(v) for v in a]
    bx, by, bw, bh = [float(v) for v in b]
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, right-left) * max(0, bottom-top)
    union = aw*ah + bw*bh - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class Track:
    id: int
    box: np.ndarray
    label: str = "IRRELEVANT"
    name: str = ""
    person_id: int | None = None
    missed: int = 0
    last_recognition: int = -1000
    last_score: float = -1.0


class FaceTracker:
    def __init__(self):
        self.tracks = []
        self.next_id = 1
        self.frame_no = 0

    def reset(self):
        self.tracks = []
        self.next_id = 1
        self.frame_no = 0

    def update(self, faces):
        self.frame_no += 1
        boxes = [np.asarray(face[:4], dtype=np.float32) for face in faces]
        unmatched = set(range(len(boxes)))
        # Priority match by IoU, then allow small movements by center distance.
        for tr in self.tracks:
            best_idx, best_rating = None, -1.0
            for idx in unmatched:
                box = boxes[idx]
                overlap = intersection_over_union(tr.box, box)
                cx1, cy1 = tr.box[0] + tr.box[2] / 2, tr.box[1] + tr.box[3] / 2
                cx2, cy2 = box[0] + box[2] / 2, box[1] + box[3] / 2
                dist = np.hypot(cx1-cx2, cy1-cy2)
                radius = max(tr.box[2], tr.box[3], box[2], box[3])
                if overlap < 0.15 and dist > radius * 0.4:
                    continue
                rating = overlap - 0.2 * dist / max(radius, 1)
                if rating > best_rating:
                    best_idx, best_rating = idx, rating
            if best_idx is None:
                tr.missed += 1
            else:
                unmatched.remove(best_idx)
                tr.box = 0.55 * boxes[best_idx] + 0.45 * tr.box
                tr.missed = 0
                tr._face_idx = best_idx
        self.tracks = [tr for tr in self.tracks if tr.missed <= 5]
        for idx in unmatched:
            tr = Track(id=self.next_id, box=boxes[idx])
            self.next_id += 1
            tr._face_idx = idx
            self.tracks.append(tr)
        return [tr for tr in self.tracks if tr.missed == 0]
