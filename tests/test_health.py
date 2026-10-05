"""Health-probe tests — plain runner. Run: py -3.11 tests/test_health.py

Offline: classification logic, pHash behaviour on synthetic images, tool
resolution, and skip-dispatch. Live probes are exercised by real sweeps.
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from wfd import health


def test_classify_stream():
    assert health.classify_stream(False, False) == "dead"
    assert health.classify_stream(True, False) == "dead"
    assert health.classify_stream(True, True) == "live"
    assert health.classify_stream(True, True, froze=True) == "stale"
    assert health.classify_stream(True, True, black=True) == "stale"


def test_classify_jpeg():
    assert health.classify_jpeg(False, None) == "unknown"
    assert health.classify_jpeg(True, None) == "unknown"
    assert health.classify_jpeg(True, 0) == "stale"
    assert health.classify_jpeg(True, 5) == "stale"
    assert health.classify_jpeg(True, 6) == "live"
    assert health.classify_jpeg(True, 22) == "live"


def test_classify_youtube():
    assert health.classify_youtube(0) == "live"
    assert health.classify_youtube(101) == "dead"
    assert health.classify_youtube(1) == "unknown"


def test_phash_synthetic():
    from PIL import Image, ImageDraw

    def png(img) -> bytes:
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    a = Image.new("RGB", (128, 128), (90, 90, 90))
    d = ImageDraw.Draw(a)
    d.rectangle([10, 10, 60, 60], fill=(200, 30, 30))
    a_bytes = png(a)

    # identical => distance 0
    assert health.phash_hamming(a_bytes, a_bytes) == 0

    # visibly different => distance > 5
    b = Image.new("RGB", (128, 128), (10, 40, 120))
    db = ImageDraw.Draw(b)
    db.rectangle([70, 70, 120, 120], fill=(255, 255, 0))
    assert health.phash_hamming(a_bytes, png(b)) > 5

    # undecodable input => None
    assert health.phash_hamming(b"not an image", a_bytes) is None


def test_tool_resolution():
    assert health._tool("ffprobe"), "ffprobe must resolve on this host"
    assert health._tool("ffmpeg"), "ffmpeg must resolve on this host"


def test_probe_row_skip_dispatch():
    res = health.probe_row("https://example.com/page", "iframe")
    assert res.state == "unknown" and res.kind == "skipped", res


def test_looks_like_image():
    assert health._looks_like_image(b"\xff\xd8" + b"0" * 20) is True
    assert health._looks_like_image(b"<html>nope</html>" * 3) is False
    assert health._looks_like_image(None) is False


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
