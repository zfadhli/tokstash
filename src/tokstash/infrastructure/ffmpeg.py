"""Segment downloader using ffmpeg with stall detection."""

import os
import subprocess
import time
from pathlib import Path

STALL_SECONDS = 15
"""int: Seconds of no file growth before considering the stream stalled."""

MIN_SEGMENT_BYTES = 1_048_576  # 1 MiB
"""int: Minimum acceptable segment size in bytes. Smaller files are discarded."""


class SegmentDownloader:
    """Download a single livestream segment via ffmpeg with stall detection.

    Spawns ffmpeg to capture *duration* seconds of the stream as MPEG-TS.
    While ffmpeg runs, monitors the output file every second. If the file
    doesn't grow for *STALL_SECONDS*, terminates ffmpeg early (stall
    detection). Discards segments smaller than *MIN_SEGMENT_BYTES*.
    """

    def __init__(self, stall_seconds: int = STALL_SECONDS, min_bytes: int = MIN_SEGMENT_BYTES):
        """Initialize the downloader.

        Args:
            stall_seconds: Seconds of no file growth before aborting.
            min_bytes: Minimum file size in bytes for a valid segment.
        """
        self._stall_seconds = stall_seconds
        self._min_bytes = min_bytes

    def download(
        self,
        stream_url: str,
        output_path: str | Path,
        duration: int = 60,
    ) -> bool:
        """Download one segment of a livestream via ffmpeg.

        Args:
            stream_url: The stream URL to capture (FLV or HLS).
            output_path: Where to save the .ts segment file.
            duration: Segment length in seconds.

        Returns:
            True if a valid segment was saved (file exists and > min_bytes),
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

        self._monitor_progress(proc, output_path)

        if not os.path.exists(output_path):
            return False

        size = os.path.getsize(output_path)
        if size < self._min_bytes:
            os.remove(output_path)
            return False

        size_mb = size / 1024 / 1024
        seg_name = Path(output_path).name
        print(f"\r  [{seg_name}]  ✅ {size_mb:.1f} MB")
        return True

    def _monitor_progress(self, proc: subprocess.Popen[bytes], output_path: str | Path) -> None:
        """Monitor ffmpeg progress and detect stalls.

        Args:
            proc: The running ffmpeg subprocess.
            output_path: Path to the output file being written.

        Raises:
            KeyboardInterrupt: Propagated from user's Ctrl+C during download.
        """
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
                        elif time.time() - stalled_since > self._stall_seconds:
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
