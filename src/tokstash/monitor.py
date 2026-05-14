"""Monitor a TikTok user and download livestream segments."""

import signal
import threading
import time
from pathlib import Path

from tokstash.downloader import download_segment
from tokstash.live_check import StreamInfo, get_stream_url
from tokstash.uploader import is_configured, upload_file


def _pick_url(info: StreamInfo) -> str | None:
    return info.flv_hd or info.flv_ld or info.hls_hd or info.hls_ld


def run_download(
    username: str,
    out: Path,
    seg_sec: int,
    start_counter: int = 1,
    running_signal: list[bool] | None = None,
) -> tuple[int, int]:
    """Download segments until the stream ends.

    Uploads happen in background threads so the next segment starts
    downloading immediately instead of waiting for the upload.

    Returns (segments_downloaded, total_bytes).
    """
    seg_counter = start_counter
    total_bytes = 0
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

        ok = download_segment(stream_url, seg_path, seg_sec)
        if ok:
            total_bytes += seg_path.stat().st_size
            seg_counter += 1
            seg_num = seg_counter
            file_size = seg_path.stat().st_size / 1024 / 1024
            print(f"       💾 {file_size:.1f} MB")

            if is_configured():
                # Upload in background — don't block the next segment
                def _upload(p: Path, n: int) -> None:
                    ok = upload_file(p, f"@{username} #{n}")
                    print(f"       📤 Telegram #{n}: {'✅' if ok else '❌'}")

                t = threading.Thread(target=_upload, args=(seg_path, seg_num), daemon=True)
                t.start()
                pending_uploads.append(t)
        else:
            break

    # Wait for any remaining uploads to finish
    for t in pending_uploads:
        t.join()

    return seg_counter - start_counter, total_bytes


def run_monitor(
    username: str,
    output_dir: str | Path,
    segment_minutes: int = 1,
    retry_seconds: int = 180,
) -> None:
    """Monitor a user and download livestream segments until interrupted.

    Checks every ``retry_seconds`` when offline. When the user goes live,
    downloads segments until the stream ends, then waits and checks again.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    total_segments = 0
    running = [True]

    def handle_sigint(*_args: object) -> None:
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
