"""Download a single livestream segment via ffmpeg with stall detection."""

import os
import subprocess
import time
from pathlib import Path

STALL_SECONDS = 15
"""int: Seconds of no file growth before considering the stream stalled."""

MIN_SEGMENT_BYTES = 1_048_576  # 1 MiB
"""int: Minimum acceptable segment size in bytes. Smaller files are discarded."""


def download_segment(
    stream_url: str,
    output_path: str | Path,
    duration: int = 60,
) -> bool:
    """Download one segment of a livestream via ffmpeg.

    Spawns ffmpeg to capture *duration* seconds of the stream as MPEG-TS.
    While ffmpeg runs, monitors the output file every second. If the file
    doesn't grow for *STALL_SECONDS*, terminates ffmpeg early (stall
    detection). Discards segments smaller than *MIN_SEGMENT_BYTES*.

    Args:
        stream_url: The stream URL to capture (FLV or HLS).
        output_path: Where to save the .ts segment file.
        duration: Segment length in seconds.

    Returns:
        True if a valid segment was saved (file exists and > 1 MB),
        False otherwise.

    Raises:
        KeyboardInterrupt: Propagated from user's Ctrl+C during download.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        stream_url,
        "-t",
        str(duration),
        "-c",
        "copy",
        "-f",
        "mpegts",
        str(output_path),
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start = time.time()
    last_size = 0
    stalled_since: float | None = None
    seg_name = Path(output_path).name

    try:
        while proc.poll() is None:
            elapsed = int(time.time() - start)
            m, s = divmod(elapsed, 60)
            print(f"\r  [{seg_name}]  ({m}:{s:02d})        ", end="", flush=True)

            try:
                cur = os.path.getsize(output_path)
                if cur == last_size:
                    if stalled_since is None:
                        stalled_since = time.time()
                    elif time.time() - stalled_since > STALL_SECONDS:
                        print(f"\r  [{seg_name}]  (stalled)")
                        proc.terminate()
                        break
                else:
                    stalled_since = None
                    last_size = cur
            except OSError:
                pass  # file not created yet

            time.sleep(1)

        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        raise

    if not os.path.exists(output_path):
        return False

    size = os.path.getsize(output_path)
    if size < MIN_SEGMENT_BYTES:
        os.remove(output_path)
        return False

    size_mb = size / 1024 / 1024
    print(f"\r  [{seg_name}]  ✅ {size_mb:.1f} MB")
    return True
