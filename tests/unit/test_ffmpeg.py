"""Tests for SegmentDownloader — constants and contract."""

from tokstash.infrastructure.ffmpeg import MIN_SEGMENT_BYTES, STALL_SECONDS


class TestConstants:
    """Module-level constants."""

    def test_stall_seconds(self) -> None:
        assert STALL_SECONDS == 15

    def test_min_bytes(self) -> None:
        assert MIN_SEGMENT_BYTES == 1_048_576


class TestSegmentDownloaderConstruction:
    """SegmentDownloader construction and defaults."""

    def test_default_values(self) -> None:
        from tokstash.infrastructure.ffmpeg import SegmentDownloader

        d = SegmentDownloader()
        assert d._stall_seconds == 15
        assert d._min_bytes == 1_048_576

    def test_custom_values(self) -> None:
        from tokstash.infrastructure.ffmpeg import SegmentDownloader

        d = SegmentDownloader(stall_seconds=30, min_bytes=512)
        assert d._stall_seconds == 30
        assert d._min_bytes == 512
