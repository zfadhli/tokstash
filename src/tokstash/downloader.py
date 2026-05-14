"""Download a single livestream segment via ffmpeg with stall detection."""

import os
import subprocess
import time
from pathlib import Path

STALL_SECONDS = 15  # kill segment if file doesn't grow for this long


def download_segment(
    stream_url: str,
    output_path: str | Path,
    duration: int = 60,
) -> bool:
    """Download one segment of the livestream.

    Returns True if the segment was successfully downloaded
    (file exists and > 1 MB), False otherwise.
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

            # Stall detection — file hasn't grown in 15s
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
    if size < 1024 * 1024:
        os.remove(output_path)
        return False

    size_mb = size / 1024 / 1024
    print(f"\r  [{seg_name}]  ✅ {size_mb:.1f} MB")
    return True
