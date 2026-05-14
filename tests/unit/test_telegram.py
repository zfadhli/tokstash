"""Tests for TelegramUploader — multipart construction."""

from pathlib import Path

from tokstash.infrastructure.telegram import TelegramUploader


class TestTelegramMultipart:
    """TelegramUploader._build_multipart — multipart form-data construction."""

    def test_builds_valid_multipart(self, tmp_segment: Path) -> None:
        """Produces correctly structured multipart body."""
        boundary = b"----TestBoundary"
        body = TelegramUploader._build_multipart(boundary, "12345", "segment.mp4", tmp_segment)

        assert body.startswith(b"--" + boundary)
        assert body.endswith(b"--" + boundary + b"--\r\n")
        assert b'name="chat_id"' in body
        assert b"12345" in body
        assert b'name="video"' in body
        assert b'filename="segment.mp4"' in body
        assert b"Content-Type: video/mp4" in body
        assert b"\x00" * 100 in body

    def test_boundary_consistency(self, tmp_segment: Path) -> None:
        """Same boundary used throughout."""
        boundary = b"----Custom"
        body = TelegramUploader._build_multipart(boundary, "999", "clip.mp4", tmp_segment)
        assert body.count(b"--" + boundary) >= 2

    def test_empty_file(self, tmp_path: Path) -> None:
        """Handles empty file content."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        body = TelegramUploader._build_multipart(b"----B", "1", "empty.mp4", empty)
        assert b"\r\n\r\n\r\n" in body

    def test_is_configured(self) -> None:
        """is_configured returns bool (depends on env)."""
        result = TelegramUploader.is_configured()
        assert isinstance(result, bool)
