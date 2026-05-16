"""Client for TikTok live page scraping with WAF bypass."""

import re
import time
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
    """

    def user_exists(self, username: str) -> bool | None:
        """Check if a TikTok account exists (regardless of live status).

        Makes up to three HTTP requests to the user's live page. TikTok
        sometimes returns a WAF challenge page (~1.4 KB with ``slardar``)
        instead of the real page, so retries are built in.

        Args:
            username: TikTok username (without @ prefix).

        Returns:
            ``True`` if the account exists.
            ``False`` if the account definitely does not exist.
            ``None`` if the check was inconclusive (all requests hit a
            challenge page).
        """
        for attempt in range(3):
            try:
                resp = requests.get(
                    TIKTOK_LIVE_URL.format(username=username),
                    headers=REQUEST_HEADERS,
                    impersonate="chrome120",
                )
            except Exception:
                continue

            if resp.status_code != 200:
                return False

            # Tiny response (~1.4 KB) with slardar = WAF challenge page.
            # Retry instead of concluding the user doesn't exist.
            if len(resp.text) < 5000 and "slardar" in resp.text:
                time.sleep(1)
                continue

            # Real users have their uniqueId embedded in the page data.
            # Non-existent accounts return a page with no uniqueId at all.
            pattern = rf'"uniqueId"\s*:\s*"{re.escape(username)}"'
            if re.search(pattern, resp.text):
                return True

            # Full page returned but uniqueId missing — user doesn't exist.
            return False

        # All attempts hit a challenge page — inconclusive.
        return None

    def get_stream_info(self, username: str) -> Optional[StreamInfo]:
        """Fetch the TikTok live page and extract stream URLs.

        Makes a single HTTP request to the user's live page. If the page
        indicates the user is live, parses stream URLs from the HTML using
        regex (both FLV and HLS variants at HD and LD quality).

        The best stream URL is then probed with a lightweight Range GET.
        TikTok's CDN returns 404 for expired/stale URLs (stream ended
        between page load and probe), so we reject those.

        Args:
            username: TikTok username (without @ prefix).

        Returns:
            A StreamInfo with available stream URLs, or None if the user
            is offline, the page can't be loaded, or the URL is stale.
        """
        try:
            resp = requests.get(
                TIKTOK_LIVE_URL.format(username=username),
                headers=REQUEST_HEADERS,
                impersonate="chrome120",
            )
        except Exception:
            return None

        if resp.status_code != 200 or "is LIVE" not in resp.text:
            return None

        info = self._parse_stream_info(resp.text)
        if info is None:
            return None

        best = info.best_url()
        if best is None:
            return None

        # Probe the stream URL to verify it's actually serving data.
        # TikTok's CDN expires URLs very quickly after a stream ends.
        if not self._probe_stream_url(best):
            return None

        return info

    @staticmethod
    def _probe_stream_url(url: str) -> bool:
        """Quick-check whether a stream URL is actually serving data.

        Uses ffprobe with a 2-second timeout. TikTok's CDN returns 404
        (via HTTP) or simply stops responding for expired URLs — ffprobe
        detects this instantly and exits with code 1. For a live stream
        ffprobe connects and returns code 0.

        Args:
            url: The stream URL to probe.

        Returns:
            True if the URL appears to be serving a live stream,
            False if it's stale/unreachable.
        """
        import subprocess

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-t",
            "2",
            "-i",
            url,
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

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
