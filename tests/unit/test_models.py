"""Tests for models — domain models."""

import pytest

from tokstash.models.stream import StreamInfo


class TestStreamInfo:
    """StreamInfo — stream data model."""

    def test_minimal(self) -> None:
        """Can create with just room_id."""
        info = StreamInfo(room_id="12345")
        assert info.room_id == "12345"
        assert info.flv_hd is None

    def test_full(self) -> None:
        """All fields settable."""
        info = StreamInfo(
            room_id="1",
            flv_hd="https://hd.flv",
            flv_ld="https://ld.flv",
            hls_hd="https://hd.m3u8",
            hls_ld="https://ld.m3u8",
        )
        assert info.flv_hd == "https://hd.flv"
        assert info.hls_ld == "https://ld.m3u8"

    def test_room_id_required(self) -> None:
        """room_id is required."""
        with pytest.raises(Exception):
            StreamInfo()  # type: ignore[call-arg]

    def test_best_url_priority(self) -> None:
        """best_url follows FLV HD → FLV LD → HLS HD → HLS LD."""
        assert StreamInfo(room_id="1", flv_hd="a").best_url() == "a"
        assert StreamInfo(room_id="1", flv_ld="b").best_url() == "b"
        assert StreamInfo(room_id="1", hls_hd="c").best_url() == "c"
        assert StreamInfo(room_id="1", hls_ld="d").best_url() == "d"

    def test_best_url_none(self) -> None:
        """best_url returns None when no URLs."""
        assert StreamInfo(room_id="1").best_url() is None
