"""Optional local MJPEG transport diagnostic; does not change any user data."""
from __future__ import annotations

import sys
import time
from mjpeg_capture import MjpegCapture, MJPEGStreamError

URL = "http://127.0.0.1:8765/stream.mjpg"


def main():
    print("=" * 57)
    print("THE MACHINE | LOCAL MJPEG CONNECTION SELF-TEST")
    print("URL:", URL)
    print("NOTE: keep 04_START_LOCAL_TEST_STREAM.bat running first.")
    print("=" * 57, flush=True)
    capture = None
    try:
        start = time.monotonic()
        capture = MjpegCapture(URL, timeout=8)
        print("[OK] HTTP/MJPEG connection established in %.2fs" % (time.monotonic() - start))
        for number in range(1, 4):
            ok, image = capture.read()
            if not ok:
                raise RuntimeError("Frame %d failed: %s" % (number, capture.last_error))
            print("[OK] Decoded frame %d: %s" % (number, image.shape))
        print("[PASS] The local MJPEG camera works with the new reader.")
        return 0
    except (MJPEGStreamError, RuntimeError, OSError) as exc:
        print("[FAIL]", exc)
        print("Check: 1) Test-stream window remains open; 2) URL is /stream.mjpg;"
              " 3) no proxy/security tool intercepts 127.0.0.1.")
        return 1
    finally:
        if capture is not None:
            capture.release()


if __name__ == "__main__":
    sys.exit(main())
