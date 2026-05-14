"""Upload downloaded segments to Telegram instead of keeping them on disk.

Requires environment variables:
    TELEGRAM_BOT_TOKEN  - bot token from @BotFather
    TELEGRAM_CHAT_ID    - chat/user ID to send files to

Also auto-loads from a .env file in the project root.
If either is missing, files stay on disk (no Telegram upload).
"""

import os
import subprocess
from pathlib import Path


def _load_dotenv() -> None:
    """Load .env file if it exists next to pyproject.toml or cwd."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
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

API_URL = "https://api.telegram.org/bot{token}/sendVideo"


def is_configured() -> bool:
    """Check if Telegram upload is configured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return bool(token and chat_id)


def _remux_to_mp4(ts_path: Path) -> Path | None:
    """Remux .ts to .mp4 (fast, no re-encode, just container change).

    Returns path to the mp4 file, or None on failure.
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


def upload_file(file_path: str | Path, caption: str = "") -> bool:
    """Upload a file to Telegram as a video and delete local files on success."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    ts_path = Path(file_path)
    if not ts_path.exists():
        return False

    # Remux to MP4 so Telegram shows it as a playable video
    mp4_path = _remux_to_mp4(ts_path)
    if not mp4_path:
        return False  # keep original file if remux fails

    try:
        boundary = b"----TikTokLiveBoundary"
        body = _build_multipart(boundary, chat_id, caption or mp4_path.name, mp4_path)
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            API_URL.format(token=token),
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


def _build_multipart(boundary: bytes, chat_id: str, filename: str, path: Path) -> bytes:
    """Build a multipart/form-data body for file upload."""
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
