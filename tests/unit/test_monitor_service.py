"""Tests for MonitorService — orchestration layer.

Uses mock infrastructure to avoid network/ffmpeg calls.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from tokstash.models.stream import StreamInfo
from tokstash.services.monitor import MonitorService


class TestMonitorService:
    """MonitorService construction and delegation."""

    def test_construction_defaults(self) -> None:
        """Creates with default infrastructure instances."""
        svc = MonitorService()
        assert svc._tiktok is not None
        assert svc._downloader is not None
        assert svc._uploader is not None

    def test_construction_with_mocks(self) -> None:
        """Accepts injected mock dependencies."""
        tiktok = MagicMock()
        dl = MagicMock()
        ul = MagicMock()
        svc = MonitorService(tiktok_client=tiktok, downloader=dl, uploader=ul)
        assert svc._tiktok is tiktok
        assert svc._downloader is dl
        assert svc._uploader is ul

    def test_download_until_ends_returns_zeroes_when_offline(self) -> None:
        """No segments when user is offline."""
        tiktok = MagicMock()
        tiktok.get_stream_info.return_value = None
        svc = MonitorService(tiktok_client=tiktok)
        n, nbytes = svc.download_until_ends("testuser", "/tmp/out", 60)
        assert n == 0
        assert nbytes == 0

    def test_download_until_ends_calls_downloader(self) -> None:
        """Delegates to SegmentDownloader for each segment."""
        info = StreamInfo(room_id="1", flv_hd="https://stream.flv")

        tiktok = MagicMock()
        tiktok.get_stream_info.return_value = info
        tiktok.get_stream_info.side_effect = [info, None]

        dl = MagicMock()

        def _fake_download(url: str, path: str | Path, duration: int = 60) -> bool:
            """Mock downloader that creates a real file."""
            Path(path).write_bytes(b"\x00" * (2 * 1024 * 1024))
            return True

        dl.download.side_effect = _fake_download

        svc = MonitorService(tiktok_client=tiktok, downloader=dl)

        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            n, nbytes = svc.download_until_ends("testuser", out, 60)
            assert n == 1
            assert nbytes > 0
            dl.download.assert_called_once()
