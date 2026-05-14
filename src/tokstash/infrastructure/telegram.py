"""Telegram Bot API uploader for livestream segments."""

import os
import subprocess
from pathlib import Path

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendVideo"
"""str: Telegram Bot API endpoint for sending video files."""


def _load_dotenv() -> None:
    """Load .env file if it exists next to pyproject.toml or cwd.

    Reads key=value pairs from the first .env found and sets them as
    environment variables. Only sets keys that are not already set.
    """
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

    Remuxes .ts to .mp4 (fast container change, no re-encode), uploads
    via the Bot API, and deletes local files on success.

    Requires environment variables:
        TELEGRAM_BOT_TOKEN  — bot token from @BotFather
        TELEGRAM_CHAT_ID    — chat/user ID to send files to
    """

    @staticmethod
    def is_configured() -> bool:
        """Check if Telegram upload is configured.

        Returns:
            True if both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
            environment variables are set and non-empty.
        """
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        return bool(token and chat_id)

    def upload(self, file_path: str | Path, caption: str = "") -> bool:
        """Upload a .ts segment to Telegram as a playable video.

        Remuxes the segment to .mp4, then uploads it via the Bot API
        (sendVideo). On success, both the .ts and .mp4 files are deleted
        from disk.

        Args:
            file_path: Path to the .ts segment file.
            caption: Optional caption for the Telegram message.

        Returns:
            True if the upload succeeded (HTTP 200), False otherwise.
        """
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return False

        ts_path = Path(file_path)
        if not ts_path.exists():
            return False

        mp4_path = self._remux_to_mp4(ts_path)
        if not mp4_path:
            return False

        try:
            boundary = b"----TokstashBoundary"
            body = self._build_multipart(boundary, chat_id, caption or mp4_path.name, mp4_path)
            req = __import__("urllib.request", fromlist=["Request"]).Request(
                TELEGRAM_API_URL.format(token=token),
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            )
            resp = __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=120)
            success = resp.status == 200

            if success:
                os.remove(mp4_path)
                os.remove(ts_path)

            return success
        except Exception:
            return False

    @staticmethod
    def _remux_to_mp4(ts_path: Path) -> Path | None:
        """Remux a .ts segment to .mp4 (fast container change, no re-encode).

        Uses ffmpeg with ``-c copy`` to change the container format without
        re-encoding video/audio streams. Takes approximately 1 second.

        Args:
            ts_path: Path to the .ts segment file.

        Returns:
            Path to the generated .mp4 file, or None if remuxing failed
            or produced a trivially small file.
        """
        mp4_path = ts_path.with_suffix(".mp4")
        cmd = ["ffmpeg", "-y", "-i", str(ts_path), "-c", "copy", str(mp4_path)]
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            if mp4_path.exists() and mp4_path.stat().st_size > 1024:
                return mp4_path
        except Exception:
            pass
        return None

    @staticmethod
    def _build_multipart(boundary: bytes, chat_id: str, filename: str, path: Path) -> bytes:
        """Build a multipart/form-data HTTP body for Telegram file upload.

        Constructs the raw multipart body with ``chat_id`` and ``video``
        fields, reading the file contents from *path*.

        Args:
            boundary: Unique MIME boundary bytes.
            chat_id: Telegram chat/user ID string.
            filename: Display filename for the video field.
            path: Path to the video file to include in the body.

        Returns:
            Complete multipart/form-data body as bytes.
        """
        parts = []
        parts.append(b"--" + boundary)
        parts.append('Content-Disposition: form-data; name="chat_id"'.encode())
        parts.append(b"")
        parts.append(chat_id.encode())

        parts.append(b"--" + boundary)
        parts.append(
            f'Content-Disposition: form-data; name="video"; filename="{filename}"'.encode(),
        )
        parts.append(b"Content-Type: video/mp4")
        parts.append(b"")
        parts.append(path.read_bytes())

        parts.append(b"--" + boundary + b"--")
        parts.append(b"")

        return b"\r\n".join(parts)
