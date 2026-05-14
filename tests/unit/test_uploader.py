"""Tests for uploader — Telegram upload helpers.

These test pure functions (is_configured, _build_multipart) and
avoid network calls by not setting env vars or mocking.
"""

from pathlib import Path

from tokstash.uploader import _build_multipart


class TestBuildMultipart:
    """_build_multipart — raw multipart form-data construction."""

    def test_builds_valid_multipart(self, tmp_segment: Path) -> None:
        """Produces a correctly structured multipart body."""
        boundary = b"----TestBoundary"
        body = _build_multipart(boundary, "12345", "segment.mp4", tmp_segment)

        assert body.startswith(b"--" + boundary)
        assert body.endswith(b"--" + boundary + b"--\r\n")
        assert b'name="chat_id"' in body
        assert b"12345" in body
        assert b'name="video"' in body
        assert b'filename="segment.mp4"' in body
        assert b"Content-Type: video/mp4" in body
        # File content present
        assert b"\x00" * 100 in body

    def test_boundary_is_used_consistently(self, tmp_segment: Path) -> None:
        """The same boundary string is used throughout."""
        boundary = b"----Custom"
        body = _build_multipart(boundary, "999", "clip.mp4", tmp_segment)

        assert body.count(b"--" + boundary) >= 2  # at least two field separators

    def test_empty_file_content(self, tmp_path: Path) -> None:
        """Handles files with minimal content."""
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        body = _build_multipart(b"----B", "1", "empty.mp4", empty)
        assert b"\r\n\r\n\r\n" in body  # empty file data between headers
