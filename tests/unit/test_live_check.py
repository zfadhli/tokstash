"""Tests for live_check — StreamInfo model and URL extraction."""

import pytest

from tokstash.live_check import StreamInfo


class TestStreamInfo:
    """StreamInfo Pydantic model — creation and defaults."""

    def test_minimal_stream_info(self) -> None:
        """Can create StreamInfo with just room_id."""
        info = StreamInfo(room_id="12345")
        assert info.room_id == "12345"
        assert info.flv_hd is None
        assert info.flv_ld is None
        assert info.hls_hd is None
        assert info.hls_ld is None

    def test_full_stream_info(self) -> None:
        """Can create StreamInfo with all fields."""
        info = StreamInfo(
            room_id="12345",
            flv_hd="https://example.com/hd.flv",
            flv_ld="https://example.com/ld.flv",
            hls_hd="https://example.com/hd.m3u8",
            hls_ld="https://example.com/ld.m3u8",
        )
        assert info.flv_hd == "https://example.com/hd.flv"
        assert info.hls_hd == "https://example.com/hd.m3u8"

    def test_room_id_is_required(self) -> None:
        """room_id is the only required field."""
        with pytest.raises(Exception):
            StreamInfo()  # type: ignore[call-arg]

    def test_optional_fields_default_to_none(self) -> None:
        """All URL fields default to None."""
        info = StreamInfo(room_id="abc")
        assert info.flv_hd is None
        assert info.flv_ld is None
        assert info.hls_hd is None
        assert info.hls_ld is None
