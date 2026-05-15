"""Tests for TelegramUploader — configuration and remuxing."""

from pathlib import Path

from tokstash.infrastructure.telegram import TelegramUploader


class TestTelegramUploaderConfig:
    """Construction and configuration detection."""

    def test_not_configured_with_explicit_empty(self) -> None:
        """Explicit empties are not configured."""
        uploader = TelegramUploader(bot_token="", chat_id="")
        assert not uploader.is_configured()

    def test_configured_with_explicit_args(self) -> None:
        """Explicit constructor args produce a configured uploader."""
        uploader = TelegramUploader(bot_token="tok:secret", chat_id="999")
        assert uploader.is_configured()

    def test_partial_args_not_configured(self) -> None:
        """Missing chat_id means not configured."""
        uploader = TelegramUploader(bot_token="b", chat_id="")
        assert not uploader.is_configured()


class TestRemuxToMp4:
    """_remux_to_mp4 — fast container remuxing."""

    def test_returns_none_for_nonexistent_file(self) -> None:
        """Remux returns None when input file doesn't exist."""
        result = TelegramUploader._remux_to_mp4(Path("/nonexistent/file.ts"))
        assert result is None
