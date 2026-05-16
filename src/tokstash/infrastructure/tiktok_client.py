"""Client for TikTok live page scraping with WAF bypass."""

import logging
import re
import time
from typing import Optional

from curl_cffi import requests

from tokstash.models.stream import StreamInfo

_logger = logging.getLogger(__name__)

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

TIKREC_SIGN_URL = "https://tikrec.com/tiktok/room/api/sign"
"""str: Third-party signing service for TikTok API URLs."""


class TikTokClient:
    """HTTP client for checking TikTok livestream status.

    Uses TikTok's internal Webcast API (via a signed URL) to check if a
    user is live and retrieve stream URLs. Falls back to HTML scraping
    if the signing service is unavailable.
    """

    def __init__(self, use_api: bool = True) -> None:
        """Initialize the client.

        Args:
            use_api: Whether to use the TikTok internal API (via tikrec
                signing). Set to False to force HTML scraping fallback.
        """
        self._use_api = use_api

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
            if len(resp.text) < 5000 and "slardar" in resp.text:
                time.sleep(1)
                continue

            pattern = rf'"uniqueId"\s*:\s*"{re.escape(username)}"'
            if re.search(pattern, resp.text):
                return True

            return False

        return None

    def get_stream_info(self, username: str) -> Optional[StreamInfo]:
        """Check whether *username* is live and return stream URLs.

        Uses TikTok's internal Webcast API when possible (more reliable,
        no false positives from stale rooms).  Falls back to HTML page
        scraping if the signing service is unavailable.

        The flow is:

        1. Obtain a signed API URL (via tikrec.com signing service).
        2. Fetch the user's room ID from TikTok's room API.
        3. Call the ``check_alive`` endpoint  (definitive live/not-live).
        4. Fetch stream URLs from the room info endpoint.

        When the API path succeeds (tikrec responds, check_alive returns
        a result), its answer is trusted — even when it says "offline".
        The HTML fallback only kicks in when the API is unreachable.

        Args:
            username: TikTok username (without @ prefix).

        Returns:
            A StreamInfo with stream URLs, or None if the user is offline.
        """
        # Try the API path first
        if self._use_api:
            info, api_decided = self._get_stream_info_via_api(username)
            if api_decided:
                # API successfully reached a conclusion (live or offline).
                # Trust it — don't fall back to HTML scraping.
                return info
            # API failed (tikrec down, network error), fall through to HTML

        # Fallback: HTML page scraping
        return self._get_stream_info_via_html(username)

    # ------------------------------------------------------------------
    # TikTok Internal API
    # ------------------------------------------------------------------

    def _get_stream_info_via_api(self, username: str) -> tuple[Optional[StreamInfo], bool]:
        """Fetch stream info via TikTok's internal Webcast API.

        Returns:
            Tuple of ``(info, decided)`` where *decided* is True when the
            API successfully reached a conclusion (live or offline) and
            False when the API path failed (services unreachable).
        """
        try:
            room_id = self._get_room_id(username)
            if not room_id:
                _logger.debug("API: no roomId returned")
                return None, False  # uncertain, could be API error

            alive = self._is_room_alive(room_id)
            if not alive:
                return None, True  # definitively offline

            info = self._get_stream_urls(room_id)
            return info, True  # definitively live
        except Exception:
            _logger.debug("TikTok API path failed", exc_info=True)
            return None, False

    def _get_signed_api_url(self, username: str) -> str | None:
        """Obtain a signed URL for TikTok's room API via the tikrec service.

        TikTok requires ``X-Bogus`` and ``X-Gnarly`` signing parameters
        for its internal APIs. The tikrec.com service generates these.
        """
        try:
            resp = requests.get(
                TIKREC_SIGN_URL,
                params={"unique_id": username},
                impersonate="chrome120",
                timeout=15,
            )
            data = resp.json()
            return data.get("signed_url")
        except Exception:
            _logger.debug("Failed to get signed URL from tikrec", exc_info=True)
            return None

    def _get_room_id(self, username: str) -> str | None:
        """Fetch the user's current room ID via TikTok's internal API.

        Returns None if the user isn't currently streaming (the API
        may still return a stale roomId, which we filter with check_alive).
        """
        signed_url = self._get_signed_api_url(username)
        if not signed_url:
            return None

        resp = requests.get(
            signed_url,
            headers={"Referer": "https://www.tiktok.com/"},
            impersonate="chrome120",
            timeout=15,
        )
        data = resp.json()
        return (data.get("data") or {}).get("user", {}).get("roomId")

    def _is_room_alive(self, room_id: str) -> bool:
        """Definitive live/not-live check via TikTok's Webcast API."""
        resp = requests.get(
            f"https://webcast.tiktok.com/webcast/room/check_alive/?aid=1988&room_ids={room_id}",
            headers={"Referer": "https://www.tiktok.com/"},
            impersonate="chrome120",
            timeout=15,
        )
        data = resp.json()
        return bool((data.get("data") or [{}])[0].get("alive"))

    def _get_stream_urls(self, room_id: str) -> StreamInfo | None:
        """Fetch stream URLs via TikTok's Webcast room info API.

        Returns a StreamInfo populated with FLV and HLS URLs at the
        best available quality, or None if the API request fails.
        """
        resp = requests.get(
            f"https://webcast.tiktok.com/webcast/room/info/?aid=1988&room_id={room_id}",
            headers={"Referer": "https://www.tiktok.com/"},
            impersonate="chrome120",
            timeout=15,
        )
        data = resp.json()
        stream_url = (data.get("data") or {}).get("stream_url", {})

        flv_pull = stream_url.get("flv_pull_url", {})
        if not flv_pull:
            return None

        # Pick best FLV quality
        best_flv = None
        for q in ("FULL_HD1", "HD1", "SD1", "SD2"):
            if q in flv_pull:
                best_flv = flv_pull[q]
                break

        if not best_flv:
            return None

        # Build StreamInfo
        is_hd = best_flv == flv_pull.get("FULL_HD1") or best_flv == flv_pull.get("HD1")
        return StreamInfo(
            room_id=room_id,
            flv_hd=best_flv if is_hd else None,
            flv_ld=best_flv if not is_hd else flv_pull.get("SD1") or flv_pull.get("SD2"),
        )

    # ------------------------------------------------------------------
    # HTML scraping fallback (original approach)
    # ------------------------------------------------------------------

    def _get_stream_info_via_html(self, username: str) -> Optional[StreamInfo]:
        """Fallback: scrape stream info from the TikTok live page HTML."""
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

        if info.best_url() is None:
            return None

        return info

    @staticmethod
    def _parse_stream_info(html: str) -> StreamInfo | None:
        """Extract StreamInfo from TikTok live page HTML (fallback path)."""
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
