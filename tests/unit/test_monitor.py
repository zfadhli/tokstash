"""Tests for monitor — _pick_url and stream URL selection."""

from tokstash.live_check import StreamInfo
from tokstash.monitor import _pick_url


class TestPickUrl:
    """_pick_url — stream URL priority selection."""

    def test_returns_flv_hd_when_available(self) -> None:
        """Returns the highest quality FLV URL."""
        info = StreamInfo(
            room_id="1",
            flv_hd="https://hd.flv",
            flv_ld="https://ld.flv",
            hls_hd="https://hd.m3u8",
            hls_ld="https://ld.m3u8",
        )
        assert _pick_url(info) == "https://hd.flv"

    def test_falls_back_to_flv_ld(self) -> None:
        """Falls back to FLV LD when HD is unavailable."""
        info = StreamInfo(room_id="1", flv_ld="https://ld.flv")
        assert _pick_url(info) == "https://ld.flv"

    def test_falls_back_to_hls_hd(self) -> None:
        """Falls back to HLS HD when no FLV streams."""
        info = StreamInfo(room_id="1", hls_hd="https://hd.m3u8")
        assert _pick_url(info) == "https://hd.m3u8"

    def test_falls_back_to_hls_ld(self) -> None:
        """Falls back to HLS LD as last resort."""
        info = StreamInfo(room_id="1", hls_ld="https://ld.m3u8")
        assert _pick_url(info) == "https://ld.m3u8"

    def test_returns_none_when_no_streams(self) -> None:
        """Returns None when no stream URLs are available."""
        info = StreamInfo(room_id="1")
        assert _pick_url(info) is None
