"""wfd.health — liveness probes (the WORKING/LIVE proof) + health sweeps.

Implements the A1 doctrine (research/ingest/S4-verification-selfheal.md):

  streams (hls/mjpeg):  structure (ffprobe must show a video track)
                        -> decode proof (`-t 1 -f null -`, rc 0)
                        -> motion pass (blackdetect + freezedetect over a window)
  stills  (jpeg):       two-sample pHash — changed => live; identical => stale
                        (static-suspect; refresh cadence is dataset-specific)
  youtube:              `yt-dlp --simulate --break-match-filter is_live` (rc 0 = live)

Honest states only: live / stale / dead / unknown. Probing is bounded and
polite (global worker cap + per-host concurrency cap + start spacing), and is
NEVER applied to exposure rows — selection is restricted to
`provenance='public_by_design'` in the SQL itself.

Every result writes back to the registry (`status`, `last_verified`) and to an
evidence JSONL (`data/health/health-<slice>-<ts>.jsonl`). Sweeps are resumable:
rows already checked today are skipped unless `--recheck`.

CLI (registered via wfd.cli):
    py -3.11 -m wfd health probe <url> [--kind hls|jpeg|youtube]
    py -3.11 -m wfd health run --family nsw [--limit N] [--workers N]
                               [--gap-s 30] [--freeze-s 6] [--protocol jpeg]
                               [--filter "SQL AND-fragment"] [--recheck]
"""
from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from . import db as dbmod
from . import profile
from .ingest.base import DATA_DIR
from .schema import Health

IS_WINDOWS = sys.platform == "win32"
_CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
HEALTH_DIR = DATA_DIR / "health"

# classification thresholds (calibrated on real data — see PLAN A12)
JPEG_STATIC_MAX = 5        # hamming <= this => static-suspect (stale)
FREEZE_D_FAIL_S = 1.0      # freezedetect: no-change duration to trigger


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# tool resolution (PATH first, then known fallbacks; version drift tolerated)
# ---------------------------------------------------------------------------

_TOOL_CACHE: dict = {}


def _tool(name: str) -> Optional[str]:
    if name in _TOOL_CACHE:
        return _TOOL_CACHE[name]
    found = shutil.which(name)
    if found is None:
        home = pathlib.Path.home()
        candidates = [
            home / "AppData/Local/hermes/tools/ffmpeg-9.0.1-win32-x64/bin" / f"{name}.exe",
            home / "AppData/Local/Programs/Python/Python311/Scripts" / f"{name}.exe",
        ]
        base = home / "AppData/Local/hermes/tools"
        if base.exists():
            for d in sorted(base.glob("ffmpeg-*")):
                candidates.extend([d / "bin" / f"{name}.exe", d / "bin" / name])
        for c in candidates:
            if c.exists():
                found = str(c)
                break
    _TOOL_CACHE[name] = found
    return found


def _run(cmd: list, timeout: float) -> tuple:
    """Run a subprocess (no console window). Returns (rc, stdout, stderr) strings."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=_CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
        )
        return (
            p.returncode,
            (p.stdout or b"").decode("utf-8", "replace"),
            (p.stderr or b"").decode("utf-8", "replace"),
        )
    except subprocess.TimeoutExpired:
        return -9, "", "timeout"
    except FileNotFoundError:
        return -1, "", "tool not found"
    except Exception as exc:  # noqa: BLE001
        return -2, "", f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# per-host politeness gate (concurrency cap + start spacing)
# ---------------------------------------------------------------------------

class HostGate:
    """Caps concurrent probes per host and spaces probe starts."""

    def __init__(self, cap: int = 4, spacing: float = 0.5):
        self.cap = cap
        self.spacing = spacing
        self._lock = threading.Lock()
        self._sems: dict = {}
        self._last: dict = {}

    def _sem(self, host: str) -> threading.Semaphore:
        with self._lock:
            if host not in self._sems:
                self._sems[host] = threading.Semaphore(self.cap)
            return self._sems[host]

    def acquire(self, host: str) -> None:
        self._sem(host).acquire()
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait = last + self.spacing - now
            self._last[host] = max(now, last + self.spacing)
        if wait > 0:
            time.sleep(wait)

    def release(self, host: str) -> None:
        self._sem(host).release()


# ---------------------------------------------------------------------------
# probe results + pure classification (unit-tested)
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    url: str
    kind: str                                   # hls | mjpeg | jpeg | youtube | skipped
    state: str                                  # live | stale | dead | unknown
    wall_ms: int = 0
    evidence: dict = field(default_factory=dict)


def classify_stream(structure_ok: bool, decode_ok: bool,
                    froze: bool = False, black: bool = False) -> str:
    if not structure_ok or not decode_ok:
        return Health.DEAD.value
    if froze or black:
        return Health.STALE.value
    return Health.LIVE.value


def classify_jpeg(fetched_both: bool, hamming: Optional[int],
                  static_max: int = JPEG_STATIC_MAX) -> str:
    if not fetched_both:
        return Health.UNKNOWN.value
    if hamming is None:
        return Health.UNKNOWN.value
    return Health.STALE.value if hamming <= static_max else Health.LIVE.value


def classify_youtube(rc: int) -> str:
    if rc == 0:
        return Health.LIVE.value
    if rc == 101:
        return Health.DEAD.value
    return Health.UNKNOWN.value


def phash_hamming(blob_a: bytes, blob_b: bytes) -> Optional[int]:
    """Perceptual-hash distance between two images. None when undecodable."""
    try:
        from PIL import Image
        import imagehash
        h1 = imagehash.phash(Image.open(io.BytesIO(blob_a)))
        h2 = imagehash.phash(Image.open(io.BytesIO(blob_b)))
        return int(h1 - h2)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------

UA_FALLBACK = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _fetch_bytes(url: str, timeout: float = 15, ua: Optional[str] = None) -> Optional[bytes]:
    try:
        headers = {"User-Agent": ua or profile.settings().get("user_agent", "world-feed-db/0.1")}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(4_000_000)
    except Exception:  # noqa: BLE001
        return None


def _looks_like_image(blob: Optional[bytes]) -> bool:
    if not blob or len(blob) < 16:
        return False
    return (blob[:2] == b"\xff\xd8"                      # jpeg
            or blob[:8] == b"\x89PNG\r\n\x1a\n"      # png
            or blob[:3] == b"GIF"                        # gif
            or (blob[:4] == b"RIFF" and blob[8:12] == b"WEBP"))


def _fetch_image(url: str, timeout: float = 15) -> tuple:
    """Fetch an image with UA fallback. Returns (blob, stage): 'polite'|'browser'|None.

    Some hosts serve an HTML stub to non-browser User-Agents (NSW webcams do);
    stage 2 retries once with a plain browser UA and the stage is recorded in
    the probe evidence.
    """
    for stage, ua in (("polite", None), ("browser", UA_FALLBACK)):
        blob = _fetch_bytes(url, timeout, ua=ua)
        if _looks_like_image(blob):
            return blob, stage
    return None, None


def probe_stream(url: str, *, freeze_s: float = 6, timeout: float = 25) -> ProbeResult:
    """hls / mjpeg: structure -> decode -> freeze/black motion pass."""
    t0 = time.monotonic()
    ffprobe, ffmpeg = _tool("ffprobe"), _tool("ffmpeg")
    ev: dict = {}
    if not ffprobe or not ffmpeg:
        return ProbeResult(url, "hls", Health.UNKNOWN.value, 0, {"error": "ffmpeg/ffprobe not found"})

    structure_ok = False
    ua_args: list = []
    ev["ua_stage"] = "default"
    for attempt in (1, 2):
        rc, out, _ = _run(
            [ffprobe, "-v", "error", "-rw_timeout", "15000000",
             *ua_args,
             "-show_entries", "stream=codec_type,codec_name", "-of", "json", url],
            timeout,
        )
        ev["probe_rc"] = rc
        if rc == 0:
            try:
                streams = json.loads(out or "{}").get("streams", [])
                structure_ok = any(s.get("codec_type") == "video" for s in streams)
                ev["streams"] = [f"{s.get('codec_type')}:{s.get('codec_name')}" for s in streams][:4]
            except Exception:  # noqa: BLE001
                structure_ok = False
        if structure_ok:
            break
        if attempt == 1:
            ua_args = ["-user_agent", UA_FALLBACK]   # stage 2: browser UA
            ev["ua_stage"] = "browser"
            time.sleep(0.5)
    if not structure_ok:
        return ProbeResult(url, "hls", classify_stream(False, False),
                           int((time.monotonic() - t0) * 1000), ev)

    rc2, _, err2 = _run(
        [ffmpeg, "-v", "error", "-nostdin", *ua_args, "-i", url, "-t", "1", "-f", "null", "-"],
        timeout + 5,
    )
    ev["decode_rc"] = rc2
    decode_ok = rc2 == 0
    if not decode_ok:
        ev["decode_err"] = (err2 or "")[-200:]

    froze = black = False
    if decode_ok and freeze_s > 0:
        rc3, _, err3 = _run(
            [ffmpeg, "-v", "info", "-nostats", "-hide_banner", "-nostdin", *ua_args, "-i", url,
             "-t", str(freeze_s),
             "-vf", f"blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-60dB:d={FREEZE_D_FAIL_S}",
             "-f", "null", "-"],
            timeout + freeze_s + 10,
        )
        froze = "freeze_start" in (err3 or "")
        black = "black_start" in (err3 or "")
        ev["motion"] = {"rc": rc3, "freeze": froze, "black": black}

    return ProbeResult(url, "hls", classify_stream(True, decode_ok, froze, black),
                       int((time.monotonic() - t0) * 1000), ev)


def probe_jpeg(url: str, *, gap_s: float = 30, timeout: float = 15,
               static_max: int = JPEG_STATIC_MAX) -> ProbeResult:
    """jpeg: two-sample pHash (changed => live; identical => stale-suspect)."""
    t0 = time.monotonic()
    ev: dict = {}
    a, stage_a = _fetch_image(url, timeout)
    ev["fetch1"] = a is not None
    if a is None:
        a, stage_a = _fetch_image(url, timeout)
        ev["fetch1_retry"] = a is not None
    if a is None:
        return ProbeResult(url, "jpeg", Health.DEAD.value,
                           int((time.monotonic() - t0) * 1000), ev)
    ev["stage"] = stage_a

    if gap_s > 0:
        time.sleep(gap_s)
    b, _ = _fetch_image(url, timeout)
    ev["fetch2"] = b is not None
    if b is None:
        b, _ = _fetch_image(url, timeout)
    hamming = phash_hamming(a, b) if b is not None else None
    ev["hamming"] = hamming
    ev["bytes"] = [len(a), len(b) if b else 0]

    return ProbeResult(url, "jpeg", classify_jpeg(b is not None, hamming, static_max),
                       int((time.monotonic() - t0) * 1000), ev)


def probe_youtube(url: str, timeout: float = 60) -> ProbeResult:
    t0 = time.monotonic()
    ytdlp = _tool("yt-dlp")
    if not ytdlp:
        return ProbeResult(url, "youtube", Health.UNKNOWN.value, 0, {"error": "yt-dlp not found"})
    rc, _, err = _run([ytdlp, "--simulate", "--no-warnings",
                       "--break-match-filter", "is_live", url], timeout)
    ev = {"rc": rc, "stderr_tail": (err or "")[-160:]}
    return ProbeResult(url, "youtube", classify_youtube(rc),
                       int((time.monotonic() - t0) * 1000), ev)


def probe_row(url: str, protocol: str, *, gap_s: float = 30, freeze_s: float = 6) -> ProbeResult:
    if protocol in ("hls", "mjpeg"):
        return probe_stream(url, freeze_s=freeze_s)
    if protocol == "jpeg":
        return probe_jpeg(url, gap_s=gap_s)
    if protocol == "youtube":
        return probe_youtube(url)
    return ProbeResult(url, "skipped", Health.UNKNOWN.value, 0,
                       {"skipped": f"protocol {protocol!r} needs a resolver; not probed"})


# ---------------------------------------------------------------------------
# sweeps (resumable; write-back to registry + evidence JSONL)
# ---------------------------------------------------------------------------

def run_sweep(*, family: Optional[str] = None, where: Optional[str] = None,
              limit: Optional[int] = None, protocol: Optional[str] = None,
              workers: int = 8, gap_s: float = 30, freeze_s: float = 6,
              recheck: bool = False, host_cap: int = 4) -> dict:
    conn = dbmod.connect()
    dbmod.init_db(conn)

    q = ("SELECT camera_id, url, protocol, source_family FROM cameras "
         "WHERE provenance='public_by_design' "
         "AND protocol IN ('hls','mjpeg','jpeg','youtube')")
    params: list = []
    if family:
        q += " AND source_family=?"
        params.append(family)
    if protocol:
        q += " AND protocol=?"
        params.append(protocol)
    if where:
        q += f" AND ({where})"
    if not recheck:
        q += " AND (last_verified='' OR last_verified NOT LIKE ?)"
        params.append(_today() + "%")
    q += " ORDER BY rowid"
    if limit:
        q += f" LIMIT {int(limit)}"

    rows = conn.execute(q, params).fetchall()
    total = len(rows)
    slice_name = family or "mix"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HEALTH_DIR / f"health-{slice_name}-{ts}.jsonl"
    out_fh = out_path.open("w", encoding="utf-8")
    lock = threading.Lock()
    counts = {"live": 0, "stale": 0, "dead": 0, "unknown": 0}
    done = 0
    t0 = time.monotonic()
    gate = HostGate(cap=host_cap, spacing=0.5)

    print(f"slice: family={family} protocol={protocol or 'any'} selected={total} "
          f"workers={workers} gap_s={gap_s} freeze_s={freeze_s} -> {out_path.name}")
    if total == 0:
        print("nothing to do (all rows checked today? use --recheck)")
        out_fh.close()
        return {"selected": 0, "counts": counts}

    def work(row):
        nonlocal done
        cid, url, proto, fam = row["camera_id"], row["url"], row["protocol"], row["source_family"]
        host = url.split("/")[2] if "//" in url else url
        gate.acquire(host)
        try:
            res = probe_row(url, proto, gap_s=gap_s, freeze_s=freeze_s)
        finally:
            gate.release(host)
        checked = _now_iso()
        with lock:
            conn.execute("UPDATE cameras SET status=?, last_verified=? WHERE camera_id=?",
                         (res.state, checked, cid))
            conn.commit()
            out_fh.write(json.dumps({
                "camera_id": cid, "url": url, "family": fam, "protocol": proto,
                "state": res.state, "checked_at": checked, "wall_ms": res.wall_ms,
                "evidence": res.evidence,
            }, ensure_ascii=False) + "\n")
            out_fh.flush()
            counts[res.state] = counts.get(res.state, 0) + 1
            done += 1
            if done % 25 == 0 or done == total:
                print(f"  {done}/{total}  live={counts['live']} stale={counts['stale']} "
                      f"dead={counts['dead']} unknown={counts['unknown']}")
        return res

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(work, rows))
    finally:
        out_fh.close()
        conn.close()

    wall = round(time.monotonic() - t0, 1)
    print(f"done: {total} probed in {wall}s — live={counts['live']} stale={counts['stale']} "
          f"dead={counts['dead']} unknown={counts['unknown']}")
    print(f"evidence: {out_path}")
    return {"selected": total, "counts": counts, "wall_s": wall, "evidence": str(out_path)}


# ---------------------------------------------------------------------------
# CLI extension (registered by wfd.cli)
# ---------------------------------------------------------------------------

def _cmd_health(args) -> int:
    action = getattr(args, "health_action", None)
    if action is None:
        print("usage: wfd health {probe|run} ...")
        return 2

    if action == "probe":
        kind = args.kind or ("jpeg" if args.url.lower().split("?")[0].endswith((".jpg", ".jpeg")) else "hls")
        res = probe_row(args.url, kind, gap_s=args.gap_s, freeze_s=args.freeze_s)
        print(f"{res.kind} -> {res.state}  ({res.wall_ms} ms)")
        print(json.dumps(res.evidence, indent=1)[:2000])
        return 0

    if action == "run":
        run_sweep(family=args.family, where=args.filter, limit=args.limit,
                  protocol=args.protocol, workers=args.workers, gap_s=args.gap_s,
                  freeze_s=args.freeze_s, recheck=args.recheck, host_cap=args.host_cap)
        return 0
    return 2


def _add_health_arguments(parser) -> None:
    sub = parser.add_subparsers(dest="health_action")
    p = sub.add_parser("probe", help="probe a single URL and print the verdict + evidence")
    p.add_argument("url")
    p.add_argument("--kind", choices=["hls", "mjpeg", "jpeg", "youtube"], default=None)
    p.add_argument("--gap-s", type=float, default=30, dest="gap_s")
    p.add_argument("--freeze-s", type=float, default=6, dest="freeze_s")

    p = sub.add_parser("run", help="sweep a registry slice (resumable; public rows only)")
    p.add_argument("--family", default=None)
    p.add_argument("--protocol", default=None)
    p.add_argument("--filter", default=None, help="extra SQL AND-fragment (e.g. a meta filter)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--gap-s", type=float, default=30, dest="gap_s",
                   help="jpeg: seconds between the two samples")
    p.add_argument("--freeze-s", type=float, default=6, dest="freeze_s",
                   help="stream: motion-pass window seconds")
    p.add_argument("--host-cap", type=int, default=4, dest="host_cap")
    p.add_argument("--recheck", action="store_true", help="include rows already checked today")


_cmd_health.add_arguments = _add_health_arguments


def cli_commands() -> dict:
    """CLI extension hook (see wfd.cli): registers ``wfd health``."""
    return {"health": ("liveness probes: probe <url> | run (sweep)", _cmd_health)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wfd.health")
    _add_health_arguments(parser)
    args = parser.parse_args(argv)
    return _cmd_health(args)


if __name__ == "__main__":
    raise SystemExit(main())
