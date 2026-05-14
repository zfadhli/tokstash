"""Tests for TikTokClient — live page scraper."""

from tokstash.infrastructure.tiktok_client import TikTokClient


def _json_url(url: str) -> str:
    r"""Wrap only the protocol separator in JSON-escaping.

    Real TikTok HTML has URLs like http:\/\/example.com/stream.flv
    where only the :// part is backslash-escaped (JSON-style).
    The rest of the path uses regular forward slashes.
    """
    return url.replace("://", r":\/\/")


class TestTikTokClientParse:
    """TikTokClient._parse_stream_info — HTML parsing edge cases."""

    def test_no_room_id_returns_none(self) -> None:
        """HTML without roomId returns None."""
        client = TikTokClient()
        assert client._parse_stream_info("<html>nothing here</html>") is None

    def test_with_room_id_but_no_urls(self) -> None:
        """Room ID present but no stream URLs."""
        client = TikTokClient()
        html = '<html><script>{"roomId":"12345"}</script></html>'
        info = client._parse_stream_info(html)
        assert info is not None
        assert info.room_id == "12345"
        assert info.flv_hd is None

    def test_parses_flv_hd_url(self) -> None:
        """Extracts FLV HD URL from raw HTML."""
        client = TikTokClient()
        url = _json_url("http://example.com/stream.flv")
        html = f'<html>{{"roomId":"42"}} "{url}"</html>'
        info = client._parse_stream_info(html)
        assert info is not None
        assert info.room_id == "42"
        assert info.flv_hd is not None
        assert "example.com/stream.flv" in str(info.flv_hd)

    def test_parses_hls_url(self) -> None:
        """Extracts HLS playlist URL."""
        client = TikTokClient()
        url = _json_url("https://example.com/index.m3u8")
        html = f'<html>{{"roomId":"1"}} "{url}"</html>'
        info = client._parse_stream_info(html)
        assert info is not None
        assert info.hls_hd is not None
        assert "index.m3u8" in str(info.hls_hd)

    def test_ld_urls_separated(self) -> None:
        """LD/SD URLs go into flv_ld, not flv_hd."""
        client = TikTokClient()
        url_ld = _json_url("http://example.com/stream_ld.flv")
        url_hd = _json_url("http://example.com/stream_hd.flv")
        html = f'<html>{{"roomId":"1"}} "{url_ld}" "{url_hd}"</html>'
        info = client._parse_stream_info(html)
        assert info is not None
        assert info.flv_hd is not None
        assert info.flv_ld is not None
        assert "hd" in info.flv_hd  # type: ignore[operator]
        assert "ld" in info.flv_ld  # type: ignore[operator]

    def test_skips_only_audio(self) -> None:
        """URLs with only_audio are excluded."""
        client = TikTokClient()
        url_audio = _json_url("http://example.com/only_audio.flv")
        url_video = _json_url("http://example.com/video.flv")
        html = f'<html>{{"roomId":"1"}} "{url_audio}" "{url_video}"</html>'
        info = client._parse_stream_info(html)
        assert info is not None
        assert info.flv_hd is not None
        assert "audio" not in info.flv_hd  # type: ignore[operator]

    def test_deduplicates_urls(self) -> None:
        """Same URL appearing multiple times is only included once."""
        client = TikTokClient()
        url = _json_url("http://example.com/stream.flv")
        html = f'<html>{{"roomId":"1"}} "{url}" "{url}"</html>'
        info = client._parse_stream_info(html)
        assert info is not None
        expected = "http://example.com/stream.flv"
        assert info.flv_hd == expected
