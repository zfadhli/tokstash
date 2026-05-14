"""Monitor a TikTok user and download livestream segments.

Provides both single-session download (``run_download``) and a persistent
24/7 monitoring loop (``run_monitor``) with automatic re-checks.
"""

import signal
import threading
import time
from pathlib import Path

from tokstash.downloader import download_segment
from tokstash.live_check import StreamInfo, get_stream_url
from tokstash.uploader import is_configured, upload_file


def _pick_url(info: StreamInfo) -> str | None:
    """Pick the best available stream URL from a StreamInfo.

    Priority order: FLV HD → FLV LD → HLS HD → HLS LD.

    Args:
        info: StreamInfo with available stream URLs.

    Returns:
        The highest-priority stream URL, or None if none are available.
    """
    return info.flv_hd or info.flv_ld or info.hls_hd or info.hls_ld


def run_download(
    username: str,
    out: Path,
    seg_sec: int,
    start_counter: int = 1,
    running_signal: list[bool] | None = None,
) -> tuple[int, int]:
    """Download segments until the stream ends.

    Each segment is captured via ffmpeg, then uploaded to Telegram in
    a background thread so the next segment starts downloading immediately.

    Args:
        username: TikTok username (without @).
        out: Directory to save segment files.
        seg_sec: Segment length in seconds.
        start_counter: Starting segment counter (used when resuming
            across monitor cycles).
        running_signal: Shared mutable flag for graceful shutdown.
            A list with one bool element; set to ``[False]`` to stop.

    Returns:
        Tuple of (segments_downloaded, total_bytes).
    """
    total_bytes = 0
    seg_counter = start_counter
    running = running_signal if running_signal is not None else [True]
    pending_uploads: list[threading.Thread] = []

    while running[0]:
        info = get_stream_url(username)
        stream_url = _pick_url(info) if info else None
        if not stream_url:
            break

        ts = time.strftime("%Y%m%d_%H%M%S")
        seg_name = f"{username}_{ts}.ts"
        seg_path = out / seg_name
        cap = f"{username}_{ts}"

        ok = download_segment(stream_url, seg_path, seg_sec)
        if ok:
            total_bytes += seg_path.stat().st_size
            seg_counter += 1
            file_size = seg_path.stat().st_size / 1024 / 1024
            print(f"       💾 {file_size:.1f} MB")

            if is_configured():

                def _upload(p: Path, c: str) -> None:
                    ok = upload_file(p, c)
                    print(f"       📤 Telegram: {'✅' if ok else '❌'}")

                t = threading.Thread(target=_upload, args=(seg_path, cap), daemon=True)
                t.start()
                pending_uploads.append(t)
        else:
            break

    for t in pending_uploads:
        t.join()

    return seg_counter - start_counter, total_bytes


def run_monitor(
    username: str,
    output_dir: str | Path,
    segment_minutes: int = 1,
    retry_seconds: int = 180,
) -> None:
    """Monitor a TikTok user 24/7 and download livestream segments.

    Checks every *retry_seconds* when the user is offline. When they go
    live, downloads segments until the stream ends, then resumes checking.
    Continues until interrupted (Ctrl+C).

    Args:
        username: TikTok username (without @).
        output_dir: Directory to save segment files.
        segment_minutes: Segment length in minutes.
        retry_seconds: Seconds to wait between checks when offline.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    total_segments = 0
    running = [True]

    def handle_sigint(*_args: object) -> None:
        """Signal handler: set running flag to False for clean shutdown."""
        running[0] = False
        print("\n⏹️  Stopped.")

    original_handler = signal.signal(signal.SIGINT, handle_sigint)
    seg_sec = segment_minutes * 60

    print(f"📡 Monitoring @{username} for livestreams")
    print(f"   📁 → {out.resolve()}")
    if is_configured():
        print("   📤 Telegram upload enabled — files deleted after upload")
    else:
        print("   💡 Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to auto-upload to Telegram")
    print("   Press Ctrl+C to stop\n")

    try:
        while running[0]:
            info = get_stream_url(username)
            stream_url = _pick_url(info) if info else None

            if not stream_url:
                if total_segments == 0:
                    print(f"🟡 @{username} is offline. Checking every {retry_seconds // 60} min...")
                else:
                    print(f"🟡 Stream ended. Checking again in {retry_seconds // 60} min...")

                for _ in range(retry_seconds):
                    if not running[0]:
                        break
                    time.sleep(1)
                continue

            print(f"🟢 @{username} is LIVE!\n")
            n, nbytes = run_download(username, out, seg_sec, total_segments + 1, running)
            total_segments += n
            total_bytes += nbytes

            mb = nbytes / 1024 / 1024
            if nbytes > 0:
                print(f"\n📊 Downloaded {mb:.1f} MB in {n} segments\n")
    finally:
        signal.signal(signal.SIGINT, original_handler)
        mb = total_bytes / 1024 / 1024
        if total_bytes > 0:
            print(f"\n📊 Total: {mb:.1f} MB across {total_segments} segments")
