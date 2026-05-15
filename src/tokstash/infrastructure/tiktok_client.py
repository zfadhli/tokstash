"""Client for TikTok live page scraping with WAF bypass."""

import os
import re
from typing import Optional

from curl_cffi import requests

from tokstash.models.stream import StreamInfo

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
"""str: Chrome 125 user-agent string for TikTok requests."""

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.tiktok.com/",
}
"""dict[str, str]: HTTP headers sent with every TikTok live page request."""

TIKTOK_LIVE_URL = "https://www.tiktok.com/@{username}/live"
"""str: URL template for a TikTok user's live page."""


class TikTokClient:
    """HTTP client for checking TikTok livestream status.

    Uses curl_cffi with Chrome TLS impersonation to bypass TikTok's WAF.
    Optionally accepts TikTok session cookies to access private,
    followers-only, or age-restricted livestreams.

    To get cookies:
    1. Log into TikTok in your browser
    2. Open DevTools → Application → Cookies → www.tiktok.com
    3. Copy key cookies (sessionid, tt_chain_token, etc.)
    4. Set TIKTOK_COOKIES in .env as semicolon-separated key=value pairs
       e.g. TIKTOK_COOKIES="sessionid=abc123; tt_chain_token=def456"
    """

    def __init__(self, cookies: str | None = None) -> None:
        """Initialize the client.

        Args:
            cookies: Semicolon-separated TikTok session cookies
                (e.g. "sessionid=abc; tt_chain_token=def").
                Defaults to TIKTOK_COOKIES env var.
        """
        raw = cookies if cookies is not None else os.environ.get("TIKTOK_COOKIES", "")
        self._cookies: dict[str, str] = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                key, _, val = part.partition("=")
                self._cookies[key.strip()] = val.strip()

    def get_stream_info(self, username: str) -> Optional[StreamInfo]:
        """Fetch the TikTok live page and extract stream URLs.

        Makes a single HTTP request to the user's live page. If cookies
        are configured, they are included for authenticated access.
        If the page indicates the user is live, parses stream URLs from
        the HTML using regex (both FLV and HLS variants at HD and LD
        quality).

        Args:
            username: TikTok username (without @ prefix).

        Returns:
            A StreamInfo with available stream URLs, or None if the user
            is offline or the page can't be loaded.
        """
        try:
            headers = dict(REQUEST_HEADERS)
            resp = requests.get(
                TIKTOK_LIVE_URL.format(username=username),
                headers=headers,
                cookies=self._cookies or None,
                impersonate="chrome120",
            )
        except Exception:
            return None

        if resp.status_code != 200 or "is LIVE" not in resp.text:
            return None

        return self._parse_stream_info(resp.text)

    @staticmethod
    def _parse_stream_info(html: str) -> StreamInfo | None:
        """Extract StreamInfo from TikTok live page HTML.

        Args:
            html: Raw HTML of the TikTok live page.

        Returns:
            Parsed StreamInfo, or None if no room ID found.
        """
        room_match = re.search(r'"roomId"\s*:\s*"(\d+)"', html)
        if not room_match:
            return None
        room_id = room_match.group(1)

        raw_urls = re.findall(
            r'https?:\\?/\\?/[^"\'\\]+?\.(?:flv|m3u8)[^"\'\\]*',
            html,
        )

        seen: set[str] = set()
        flv_hd: list[str] = []
        flv_ld: list[str] = []
        hls_hd: list[str] = []
        hls_ld: list[str] = []

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
