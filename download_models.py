"""Download pinned OpenCV Zoo ONNX weights once. Offline during actual app use."""
from __future__ import annotations
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)

MODELS = [
    {
        "name": "face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "urls": [
            "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        ],
    },
    {
        "name": "face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "urls": [
            "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
            "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        ],
    },
]


def checksum(path):
    sha = hashlib.sha256()
    with open(path, "rb") as source:
        while chunk := source.read(1024 * 1024):
            sha.update(chunk)
    return sha.hexdigest()


def download_model(model):
    target = MODEL_DIR / model["name"]
    if target.exists() and checksum(target) == model["sha256"]:
        print(f"[OK] Already installed: {target.name}", flush=True)
        return True
    if target.exists():
        target.unlink()  # invalid/corrupt file, do not use it
    temp = MODEL_DIR / (model["name"] + ".download")
    for url in model["urls"]:
        try:
            print(f"Downloading {model['name']} from {url.split('/')[2]}", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "POI-Machine-Local-Setup/1.0"})
            sha = hashlib.sha256()
            amount = 0
            with urllib.request.urlopen(req, timeout=60) as response, temp.open("wb") as output:
                while True:
                    block = response.read(1024*1024)
                    if not block:
                        break
                    output.write(block)
                    sha.update(block)
                    amount += len(block)
                    print(f"  {amount / (1024 * 1024):.1f} MB downloaded", end="\r", flush=True)
            if sha.hexdigest() != model["sha256"]:
                raise ValueError("SHA256 mismatch; rejected incomplete or incorrect model")
            temp.replace(target)
            print(f"\n[OK] Verified: {target.name}", flush=True)
            return True
        except Exception as exc:
            print(f"\n[WARN] Download attempt failed: {exc}", flush=True)
            temp.unlink(missing_ok=True)
    print(f"[ERROR] Could not download {model['name']}", flush=True)
    print("Please see README for manual download links.", flush=True)
    return False


if __name__ == "__main__":
    results = [download_model(model) for model in MODELS]
    success = all(results)
    print("Model setup successful. The application can now run offline." if success else "Model setup incomplete.")
    sys.exit(0 if success else 1)
