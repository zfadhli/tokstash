"""Upload downloaded segments to Telegram using python-telegram-bot.

Requires environment variables:
    TELEGRAM_BOT_TOKEN  — bot token from @BotFather
    TELEGRAM_CHAT_ID    — chat/user ID to send files to

Also auto-loads from a .env file in the project root.
"""

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path

from telegram import Bot

_logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load .env file if it exists next to pyproject.toml or cwd."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = val
            break


_load_dotenv()

UPLOAD_RETRIES = 3
"""int: Number of times to retry a failed upload."""
UPLOAD_RETRY_DELAY = 2
"""int: Initial delay between upload retries (exponential backoff)."""

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
"""int: Telegram Bot API file size limit (50 MB)."""

TELEGRAM_MAX_BYTES_SAFE = int(MAX_UPLOAD_BYTES * 0.95)
"""int: Safe target size (47.5 MB) leaving margin for headers."""


class TelegramUploader:
    """Upload downloaded segments to Telegram as playable videos.

    Uses python-telegram-bot (Bot API) to send files. Remuxes .ts to
    .mp4 before sending so Telegram treats it as a playable video.

    Requires environment variables (loadable via .env):
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        """Initialize the uploader.

        Args:
            bot_token: Bot token from @BotFather. Defaults to TELEGRAM_BOT_TOKEN.
            chat_id: Chat/user ID or @username. Defaults to TELEGRAM_CHAT_ID.
        """
        self._bot_token = (
            bot_token if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        )
        self._chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")

    def is_configured(self) -> bool:
        """Check if Telegram upload is configured.

        Returns:
            True if both bot_token and chat_id are set.
        """
        return bool(self._bot_token and self._chat_id)

    def upload(self, file_path: str | Path, caption: str = "") -> bool:
        """Upload a .ts segment to Telegram as a playable video.

        Remuxes to .mp4, compresses if over Telegram's 50 MB limit, then
        sends via Bot API with retries and exponential backoff. On success,
        both .ts and .mp4 files are deleted from disk.

        Args:
            file_path: Path to the .ts segment file.
            caption: Optional caption for the message.

        Returns:
            True if upload succeeded, False otherwise.
        """
        if not self.is_configured():
            return False

        ts_path = Path(file_path)
        if not ts_path.exists():
            return False

        mp4_path = self._remux_to_mp4(ts_path)
        if not mp4_path:
            return False

        # Remove the .ts file now that .mp4 is ready — no need to keep both
        ts_path.unlink(missing_ok=True)

        # Compress if the file exceeds Telegram's 50 MB limit
        send_path = mp4_path
        if mp4_path.stat().st_size > MAX_UPLOAD_BYTES:
            print(
                f"       📦 File {mp4_path.stat().st_size / 1024 / 1024:.0f} MB exceeds"
                f" Telegram's 50 MB limit. Re-encoding..."
            )
            compressed = self._compress_to_fit(mp4_path)
            if compressed:
                mp4_path.unlink(missing_ok=True)
                send_path = compressed
            else:
                print("       ❌ Could not compress video to fit under 50 MB.")
                return False

        cap = caption or send_path.name
        last_exc: Exception | None = None

        for attempt in range(UPLOAD_RETRIES):
            try:
                success = asyncio.run(self._send(send_path, cap))
                if success:
                    send_path.unlink(missing_ok=True)
                    ts_path.unlink(missing_ok=True)
                    return True
            except Exception as exc:
                last_exc = exc
                if attempt < UPLOAD_RETRIES - 1:
                    delay = UPLOAD_RETRY_DELAY * (2**attempt)
                    print(
                        f"       🔄 Upload failed (attempt {attempt + 1}), retrying in {delay}s..."
                    )
                    time.sleep(delay)

        print(f"       ❌ Upload failed after {UPLOAD_RETRIES} attempts: {last_exc}")
        return False

    async def _send(self, mp4_path: Path, caption: str) -> bool:
        """Send a video file via Bot API.

        Args:
            mp4_path: Path to remuxed .mp4 file.
            caption: Caption text for the message.

        Returns:
            True if sent successfully.
        """
        bot = Bot(token=self._bot_token)

        # Resolve chat entity
        chat_id: str | int = self._chat_id
        if isinstance(chat_id, str) and chat_id.isdigit():
            chat_id = int(chat_id)

        with open(mp4_path, "rb") as f:
            await bot.send_video(
                chat_id=chat_id,
                video=f,
                caption=caption,
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
            )

        return True

    @staticmethod
    def _remux_to_mp4(ts_path: Path) -> Path | None:
        """Remux .ts to .mp4 (fast container change, no re-encode)."""
        mp4_path = ts_path.with_suffix(".mp4")
        cmd = ["ffmpeg", "-y", "-i", str(ts_path), "-c", "copy", str(mp4_path)]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if mp4_path.exists() and mp4_path.stat().st_size > 1024:
                return mp4_path
        except Exception:
            pass
        return None

    @staticmethod
    def _compress_to_fit(mp4_path: Path) -> Path | None:
        """Re-encode video to fit under Telegram's 50 MB limit.

        Calculates a target video bitrate based on the video duration
        and the 50 MB cap (with margin), then re-encodes using libx264.
        If the first pass doesn't shrink it enough, tries a lower CRF.

        Args:
            mp4_path: Path to the .mp4 file that exceeds 50 MB.

        Returns:
            Path to the compressed file, or None if compression failed.
        """
        import json

        compressed_path = mp4_path.with_stem(mp4_path.stem + "_compressed")

        # Get duration in seconds
        probe_cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-i",
            str(mp4_path),
            "-show_entries",
            "format=duration",
            "-of",
            "json",
        ]
        try:
            result = subprocess.run(
                probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15
            )
            data = json.loads(result.stdout)
            duration = float(data["format"]["duration"])
        except Exception:
            return None

        if duration <= 0:
            return None

        # Reserve 128 kbps for audio, rest goes to video
        # Target 95% of 50 MB to leave margin
        target_bytes = TELEGRAM_MAX_BYTES_SAFE
        audio_bitrate = 128_000  # 128 kbps
        total_bits = target_bytes * 8
        audio_bits = audio_bitrate * duration
        video_bits = total_bits - audio_bits
        video_bitrate = int(video_bits / duration)

        # Don't bother if target bitrate is unreasonably low
        if video_bitrate < 100_000:
            return None

        # Try CRF 28 first, then 32 if still too large
        for crf in (28, 32):
            out = (
                compressed_path
                if crf == 28
                else mp4_path.with_stem(mp4_path.stem + f"_compressed_{crf}")
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4_path),
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                "fast",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(out),
            ]
            try:
                subprocess.run(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300
                )
            except Exception:
                continue

            if out.exists() and out.stat().st_size > 1024:
                # Check if it fits
                if out.stat().st_size <= MAX_UPLOAD_BYTES:
                    # Cleanup intermediate files
                    if out != compressed_path:
                        compressed_path.unlink(missing_ok=True)
                        out.rename(compressed_path)
                    return compressed_path
                # Still too large, try next CRF
                if out != compressed_path:
                    out.unlink(missing_ok=True)

        compressed_path.unlink(missing_ok=True)
        return None
