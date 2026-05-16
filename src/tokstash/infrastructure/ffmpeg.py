"""Segment downloader using ffmpeg with stall detection."""

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
        running_signal: list[bool] | None = None,
    ) -> bool:
        """Download one segment of a livestream via ffmpeg.

        Args:
            stream_url: The stream URL to capture (FLV or HLS).
            output_path: Where to save the .ts segment file.
            duration: Segment length in seconds.
            running_signal: Shared mutable flag for graceful shutdown.
                A list with one bool element; set to ``[False]`` to stop.
                When the flag becomes False during a download, ffmpeg is
                terminated immediately and whatever data was captured is
                kept (even if smaller than *min_bytes*).

        Returns:
            True if a segment was saved (file exists and is non-empty),
            False otherwise.
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

        seg_path = Path(output_path)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        reason = self._monitor_progress(proc, seg_path, running_signal)

        if not seg_path.exists():
            return False

        size = seg_path.stat().st_size

        # Keep the partial file when:
        # - user pressed Ctrl+C (interrupted)
        # - the stream ended naturally before the full duration (stream_ended)
        # Discard it when ffmpeg failed to connect (stale URL) or stalled
        # with no real data.
        keep_anyway = reason in ("interrupted", "stream_ended")
        if size < self._min_bytes and not keep_anyway:
            seg_path.unlink(missing_ok=True)
            return False

        size_mb = size / 1024 / 1024
        print(f"\r  [{seg_path.name}]  ✅ {size_mb:.1f} MB")
        return True

    def _monitor_progress(
        self,
        proc: subprocess.Popen[bytes],
        seg_path: Path,
        running_signal: list[bool] | None = None,
    ) -> str:
        """Monitor ffmpeg progress and detect stalls or stream end.

        Args:
            proc: The running ffmpeg subprocess.
            seg_path: Path to the output file being written.
            running_signal: Shared mutable flag for graceful shutdown.
                When the flag becomes False, ffmpeg is terminated immediately.

        Returns:
            Reason ffmpeg stopped:
            - ``"completed"``: ffmpeg ran the full requested duration.
            - ``"stream_ended"``: ffmpeg exited early (source stream closed).
            - ``"stalled"``: terminated due to no file growth.
            - ``"interrupted"``: terminated due to Ctrl+C.

        Raises:
            KeyboardInterrupt: Propagated from user's Ctrl+C during download.
        """
        start = time.time()
        last_size = 0
        stalled_since: float | None = None
        seg_name = seg_path.name
        terminated = False

        try:
            while True:
                code = proc.poll()
                if code is not None:
                    # ffmpeg exited on its own before the full duration.
                    # Exit code 0 = stream played and then the source
                    # closed (natural end). Non-zero = connection error
                    # (stale/expired URL, server rejected us, etc.).
                    proc.wait()
                    return "stream_ended" if code == 0 else "failed"

                # Check for graceful shutdown via Ctrl+C
                if running_signal is not None and not running_signal[0]:
                    print(f"\r  [{seg_name}]  (interrupted)")
                    proc.terminate()
                    terminated = True
                    break

                elapsed = int(time.time() - start)
                m, s = divmod(elapsed, 60)
                print(f"\r  [{seg_name}]  ({m}:{s:02d})        ", end="", flush=True)

                try:
                    cur = seg_path.stat().st_size
                    if cur == last_size:
                        if stalled_since is None:
                            stalled_since = time.time()
                        elif time.time() - stalled_since > self._stall_seconds:
                            print(f"\r  [{seg_name}]  (stalled)")
                            proc.terminate()
                            terminated = True
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

        return "interrupted" if terminated else "completed"
