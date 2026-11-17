"""Offline face detection / embedding with OpenCV YuNet + SFace."""
from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
YUNET_MODEL = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODEL_DIR / "face_recognition_sface_2021dec.onnx"


def missing_models():
    return [p.name for p in (YUNET_MODEL, SFACE_MODEL) if not p.is_file()]


class FaceEngine:
    def __init__(self):
        missing = missing_models()
        if missing:
            raise FileNotFoundError("模型文件缺失：" + ", ".join(missing) + "。请先运行“02_download_models.bat”。")
        if not hasattr(cv2, "FaceDetectorYN") or not hasattr(cv2, "FaceRecognizerSF"):
            raise RuntimeError("当前 OpenCV 不支持 YuNet/SFace，请重新安装 requirements.txt。")
        self.detector = cv2.FaceDetectorYN.create(
            str(YUNET_MODEL), "", (320, 320), 0.8, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(SFACE_MODEL), "")
        self._input_size = None

    def detect(self, frame: np.ndarray) -> list[np.ndarray]:
        h, w = frame.shape[:2]
        if (w, h) != self._input_size:
            self.detector.setInputSize((w, h))
            self._input_size = (w, h)
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        return [face.copy() for face in faces]

    def encode(self, frame: np.ndarray, face: np.ndarray) -> np.ndarray:
        aligned = self.recognizer.alignCrop(frame, face)
        features = self.recognizer.feature(aligned).astype(np.float32).reshape(-1)
        norm = np.linalg.norm(features)
        if norm < 1e-9 or not np.isfinite(norm):
            raise ValueError("无法从该人脸提取可靠特征。")
        return features / norm

    def encode_photo(self, photo_path: str) -> np.ndarray:
        # imdecode works with Chinese / non-ASCII Windows paths.
        image_bytes = np.fromfile(photo_path, dtype=np.uint8)
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("无法读取图片，请使用 JPG / PNG，避免损坏的文件。")
        h, w = image.shape[:2]
        longest = max(h, w)
        if longest > 1280:
            scale = 1280.0 / longest
            image = cv2.resize(image, (round(w * scale), round(h * scale)))
        found = self.detect(image)
        if not found:
            raise ValueError("图片中没有检测到清晰人脸。请换一张正面、光线良好的照片。")
        if len(found) != 1:
            raise ValueError("一张登记照片只能包含一张人脸，请使用单人照片。")
        face = found[0]
        if min(face[2], face[3]) < 45:
            raise ValueError("照片中的人脸太小，建议换一张更清晰的照片。")
        return self.encode(image, face)


class FaceMatcher:
    """Matches embeddings against the local database with cosine similarity."""
    def __init__(self, database, threshold: float = 0.45):
        self.database = database
        self.threshold = threshold
        self.reload()

    def reload(self):
        self.samples = self.database.get_embeddings()

    def match(self, embedding: np.ndarray):
        best_person = None
        best_score = -1.0
        for person_id, name, label, saved in self.samples:
            score = float(np.dot(embedding, saved))
            if score > best_score:
                best_score = score
                best_person = (person_id, name, label)
        if best_person is not None and best_score >= self.threshold:
            return best_person, best_score
        return None, best_score
