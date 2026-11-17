"""An offline, local-only MJPEG video source for THE MACHINE testing.

Purpose: distinguish OpenCV/FFmpeg network-stream problems from unreliable public URLs.
Start with 04_START_LOCAL_TEST_STREAM.bat, then open http://127.0.0.1:8765/stream.mjpg
in THE MACHINE's network camera dialog. No external connections or camera access.
"""
from __future__ import annotations

import datetime
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import cv2
    import numpy as np
except ImportError as exc:
    raise SystemExit("Missing cv2/numpy. Run 01_install_environment.bat first.") from exc

HOST = "127.0.0.1"
PORT = 8765
BOUNDARY = b"frame"


def make_frame(number: int) -> bytes:
    width, height = 640, 360
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = (14, 10, 9)
    cv2.rectangle(image, (18, 18), (width - 19, height - 19), (135, 78, 35), 2)
    cv2.putText(image, "THE MACHINE // LOCAL STREAM", (32, 64),
                cv2.FONT_HERSHEY_SIMPLEX, 0.78, (235, 233, 232), 2, cv2.LINE_AA)
    cv2.putText(image, "NO CAMERA / NO INTERNET REQUIRED", (32, 102),
                cv2.FONT_HERSHEY_SIMPLEX, 0.53, (180, 185, 190), 1, cv2.LINE_AA)
    cx = int(100 + (number * 6) % 440)
    cy = int(210 + 45 * math.sin(number / 8.0))
    cv2.circle(image, (cx, cy), 39, (90, 205, 255), 3, cv2.LINE_AA)
    cv2.line(image, (cx-55, cy), (cx+55, cy), (90, 205, 255), 1, cv2.LINE_AA)
    cv2.line(image, (cx, cy-55), (cx, cy+55), (90, 205, 255), 1, cv2.LINE_AA)
    label = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(image, f"LOCAL STREAM ACTIVE  {label}", (32, 320),
                cv2.FONT_HERSHEY_SIMPLEX, 0.57, (240, 240, 240), 1, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        raise RuntimeError("Could not encode a test frame")
    return encoded.tobytes()


class StreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = ("<meta charset='utf-8'><title>THE MACHINE Test</title>"
                    "<h2>Local test stream</h2><img src='/stream.mjpg'>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path not in ("/stream.mjpg", "/video.mjpg"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        n = 0
        try:
            while True:
                jpeg = make_frame(n)
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                n += 1
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except OSError as exc:
            print(f"Stream closed: {exc}", flush=True)

    def log_message(self, fmt, *args):
        print("[LOCAL TEST] " + fmt % args, flush=True)


def main():
    try:
        server = ThreadingHTTPServer((HOST, PORT), StreamHandler)
    except OSError as exc:
        raise SystemExit(
            f"Cannot start local test server on {HOST}:{PORT}. "
            f"Another process may be using the port: {exc}"
        ) from exc
    print("=" * 60)
    print("THE MACHINE - Local MJPEG stream self-test")
    print("No physical webcam and no Internet are used.")
    print("This server accepts requests ONLY from this computer (127.0.0.1).")
    print(f"COPY INTO THE MACHINE: http://{HOST}:{PORT}/stream.mjpg")
    print(f"BROWSER CHECK: http://{HOST}:{PORT}/")
    print("Keep this window open. Press Ctrl+C to stop.")
    print("=" * 60, flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nTest stream stopped.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
