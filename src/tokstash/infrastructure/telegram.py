"""Upload downloaded segments to Telegram using Telethon.

Requires environment variables:
    TELEGRAM_API_ID      — API ID from https://my.telegram.org
    TELEGRAM_API_HASH    — API hash from https://my.telegram.org
    TELEGRAM_BOT_TOKEN   — bot token from @BotFather
    TELEGRAM_CHAT_ID     — chat/user ID or @username to send files to

Also auto-loads from a .env file in the project root.
"""

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo

# Re-use a single event loop and client for all uploads in a process.
# This avoids creating a new Telethon session per thread.
_loop: asyncio.AbstractEventLoop | None = None
_client: TelegramClient | None = None


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


class TelegramUploader:
    """Upload downloaded segments to Telegram as playable videos.

    Uses Telethon (MTProto) for reliable file uploads. Remuxes .ts to
    .mp4 before sending so Telegram treats it as a playable video.

    Requires environment variables (loadable via .env):
        TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    """

    def __init__(
        self,
        api_id: int | None = None,
        api_hash: str | None = None,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        """Initialize the uploader.

        Args:
            api_id: Telegram API ID. Defaults to TELEGRAM_API_ID env var.
            api_hash: Telegram API hash. Defaults to TELEGRAM_API_HASH env var.
            bot_token: Bot token from @BotFather. Defaults to TELEGRAM_BOT_TOKEN.
            chat_id: Chat/user ID or @username. Defaults to TELEGRAM_CHAT_ID.
        """
        self._api_id = api_id if api_id is not None else int(os.environ.get("TELEGRAM_API_ID", "0"))
        self._api_hash = (
            api_hash if api_hash is not None else os.environ.get("TELEGRAM_API_HASH", "")
        )
        self._bot_token = (
            bot_token if bot_token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        )
        self._chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")

    def is_configured(self) -> bool:
        """Check if Telegram upload is configured.

        Returns:
            True if api_id, api_hash, bot_token, and chat_id are all set.
        """
        return bool(self._api_id and self._api_hash and self._bot_token and self._chat_id)

    def upload(self, file_path: str | Path, caption: str = "") -> bool:
        """Upload a .ts segment to Telegram as a playable video.

        Remuxes to .mp4, then sends via Telethon. On success, both
        .ts and .mp4 files are deleted from disk.

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

        try:
            success = asyncio.run(self._async_upload(mp4_path, caption or mp4_path.name))
            if success:
                mp4_path.unlink(missing_ok=True)
                ts_path.unlink(missing_ok=True)
            return success
        except Exception:
            return False

    async def _async_upload(self, mp4_path: Path, caption: str) -> bool:
        """Send a file via Telethon.

        Args:
            mp4_path: Path to remuxed .mp4 file.
            caption: Caption text for the message.

        Returns:
            True if sent successfully.
        """
        global _loop, _client

        if _client is None:
            session_dir = Path(tempfile.gettempdir()) / "tokstash"
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = str(session_dir / "telegram_session")

            _client = TelegramClient(
                session_file,
                self._api_id,
                self._api_hash,
            )
            await _client.start(bot_token=self._bot_token)

        # Resolve chat entity (numeric ID or @username)
        entity = self._chat_id
        if entity.isdigit():
            entity = int(entity)

        await _client.send_file(
            entity,
            str(mp4_path),
            caption=caption,
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                    supports_streaming=True,
                ),
            ],
        )
        return True

    @staticmethod
    def _remux_to_mp4(ts_path: Path) -> Path | None:
        """Remux .ts to .mp4 (fast container change, no re-encode).

        Args:
            ts_path: Path to the .ts segment file.

        Returns:
            Path to .mp4, or None on failure.
        """
        mp4_path = ts_path.with_suffix(".mp4")
        cmd = ["ffmpeg", "-y", "-i", str(ts_path), "-c", "copy", str(mp4_path)]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if mp4_path.exists() and mp4_path.stat().st_size > 1024:
                return mp4_path
        except Exception:
            pass
        return None
