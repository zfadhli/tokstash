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
from telegram.error import BadRequest

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

        Remuxes to .mp4, then sends via Bot API with retries and
        exponential backoff. On success, both .ts and .mp4 files
        are deleted from disk.

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

        cap = caption or mp4_path.name
        last_exc: Exception | None = None

        for attempt in range(UPLOAD_RETRIES):
            try:
                success = asyncio.run(self._send(mp4_path, cap))
                if success:
                    mp4_path.unlink(missing_ok=True)
                    ts_path.unlink(missing_ok=True)
                    return True
            except BadRequest as exc:
                msg = str(exc).lower()
                if "too large" in msg or "entity too large" in msg or "413" in msg:
                    size_mb = mp4_path.stat().st_size / 1024 / 1024
                    print(
                        f"       ❌ File {size_mb:.0f} MB exceeds Telegram's 50 MB limit.\n"
                        f"          Increase the limit via BotFather /setuploadsize,\n"
                        f"          or use shorter segments (-s 0.5 for 30s)."
                    )
                    return False
                raise  # let the generic handler below catch it
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
