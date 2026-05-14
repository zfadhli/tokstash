"""Tests for TelegramUploader — configuration and remuxing.

The actual upload path uses Telethon (async) and real credentials,
so it's tested via integration tests. Here we test the synchronous
helpers and configuration logic.
"""

from pathlib import Path

from tokstash.infrastructure.telegram import TelegramUploader


class TestTelegramUploaderConfig:
    """Construction and configuration detection."""

    def test_not_configured_with_explicit_empty(self) -> None:
        """Construction with explicit empties is not configured."""
        uploader = TelegramUploader(api_id=0, api_hash="", bot_token="", chat_id="")
        assert not uploader.is_configured()

    def test_configured_with_explicit_args(self) -> None:
        """Explicit constructor args produce a configured uploader."""
        uploader = TelegramUploader(
            api_id=12345,
            api_hash="abc123",
            bot_token="tok:secret",
            chat_id="999",
        )
        assert uploader.is_configured()

    def test_partial_args_not_configured(self) -> None:
        """Missing chat_id means not configured."""
        uploader = TelegramUploader(api_id=1, api_hash="a", bot_token="b", chat_id="")
        assert not uploader.is_configured()


class TestRemuxToMp4:
    """_remux_to_mp4 — fast container remuxing."""

    def test_returns_none_for_nonexistent_file(self) -> None:
        """Remux returns None when input file doesn't exist."""
        result = TelegramUploader._remux_to_mp4(Path("/nonexistent/file.ts"))
        assert result is None
