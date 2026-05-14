"""Check if a TikTok user is live and extract stream URLs."""

import re
from typing import Optional

from curl_cffi import requests
from pydantic import BaseModel

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class StreamInfo(BaseModel):
    room_id: str
    flv_hd: Optional[str] = None
    flv_ld: Optional[str] = None
    hls_hd: Optional[str] = None
    hls_ld: Optional[str] = None


def get_stream_url(username: str) -> Optional[StreamInfo]:
    """Fetch the TikTok live page and extract stream URLs.

    Returns None if the user is offline or the page can't be loaded.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.tiktok.com/",
    }

    try:
        resp = requests.get(
            f"https://www.tiktok.com/@{username}/live",
            headers=headers,
            impersonate="chrome120",
        )
    except Exception:
        return None

    if resp.status_code != 200 or "is LIVE" not in resp.text:
        return None

    html = resp.text

    room_match = re.search(r'"roomId"\s*:\s*"(\d+)"', html)
    room_id = room_match.group(1) if room_match else "unknown"

    # Find raw stream URLs (JSON-escaped with \/)
    raw_urls = re.findall(
        r'https?:\\?/\\?/[^"\'\\]+?\.(?:flv|m3u8)[^"\'\\]*',
        html,
    )

    seen: set[str] = set()
    flv_hd, flv_ld, hls_hd, hls_ld = [], [], [], []

    for u in raw_urls:
        u = u.replace("\\/", "/").replace("\\u0026", "&")
        if u in seen:
            continue
        seen.add(u)

        is_flv = u.endswith(".flv") or "flv?" in u
        is_hls = "index.m3u8" in u

        if is_flv:
            if "only_audio" in u:
                continue
            if "_ld" in u or "_sd" in u:
                flv_ld.append(u)
            else:
                flv_hd.append(u)
        elif is_hls:
            if "_ld" in u or "_sd" in u:
                hls_ld.append(u)
            else:
                hls_hd.append(u)

    return StreamInfo(
        room_id=room_id,
        flv_hd=flv_hd[0] if flv_hd else None,
        flv_ld=flv_ld[0] if flv_ld else None,
        hls_hd=hls_hd[0] if hls_hd else None,
        hls_ld=hls_ld[0] if hls_ld else None,
    )
