"""Shared fixtures for tokstash tests."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_segment(tmp_path: Path) -> Path:
    """Create a minimal valid .ts segment for testing.

    Writes a 2 MiB file of null bytes to simulate a downloaded segment.
    """
    seg = tmp_path / "test_user_20260515_143012.ts"
    seg.write_bytes(b"\x00" * (2 * 1024 * 1024))  # 2 MiB
    return seg


@pytest.fixture
def small_segment(tmp_path: Path) -> Path:
    """Create a small .ts segment (< 1 MB, should be discarded)."""
    seg = tmp_path / "small_segment.ts"
    seg.write_bytes(b"\x00" * (512 * 1024))  # 512 KiB
    return seg
