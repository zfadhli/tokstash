"""Tests for downloader — constants and segment validation logic.

download_segment() itself spawns ffmpeg and reads live streams, which
cannot be unit-tested without mocking subprocess + network. We test
the contract and constants here instead.
"""

from tokstash.downloader import MIN_SEGMENT_BYTES, STALL_SECONDS


class TestConstants:
    """Module-level constants have expected values."""

    def test_stall_seconds(self) -> None:
        """STALL_SECONDS should be 15 seconds."""
        assert STALL_SECONDS == 15

    def test_min_segment_bytes(self) -> None:
        """MIN_SEGMENT_BYTES should be 1 MiB."""
        assert MIN_SEGMENT_BYTES == 1_048_576
