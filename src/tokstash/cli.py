"""CLI interface for tokstash — download and monitor TikTok livestreams.

Provides two commands via click:

- ``download``: Single-session download until the stream ends.
- ``monitor``: Persistent 24/7 monitoring with auto-download.
"""

import signal
import sys
import time
from pathlib import Path

import click

from tokstash.infrastructure.telegram import TelegramUploader
from tokstash.infrastructure.tiktok_client import TikTokClient
from tokstash.models.stream import StreamInfo
from tokstash.services.monitor import MonitorService


@click.group()
def cli() -> None:
    """Download TikTok livestreams in playable segments."""


@cli.command()
@click.argument("username")
@click.option("-o", "--output", default="./output", help="Output directory (default: ./output)")
@click.option("-s", "--segment", default=1, type=int, help="Segment length in minutes (default: 1)")
@click.option(
    "-r",
    "--retry",
    default=10,
    type=int,
    help="Seconds between checks when offline (default: 10)",
)
@click.option(
    "-m",
    "--max-retries",
    default=5,
    type=int,
    help="Max offline checks before giving up (default: 5)",
)
def download(
    username: str,
    output: str,
    segment: int,
    retry: int,
    max_retries: int,
) -> None:
    """Download livestream until the user goes offline, then stop."""
    tiktok = TikTokClient()
    uploader = TelegramUploader()
    service = MonitorService(tiktok_client=tiktok, uploader=uploader)
    out_dir = Path(output)

    # Check user exists before attempting download
    exists = tiktok.user_exists(username)
    if exists is False:
        click.echo(f"🔴 @{username} does not exist on TikTok.")
        sys.exit(1)
    elif exists is None:
        click.echo("🟡 Could not verify user — TikTok challenge page. Continuing anyway...")

    running: list[bool] = [True]

    def handle_sigint(*_args: object) -> None:
        """Signal handler: gracefully stop downloads on Ctrl+C."""
        running[0] = False
        click.echo("\n⏹️  Stopping...")

    original_handler = signal.signal(signal.SIGINT, handle_sigint)

    try:
        _wait_for_live(tiktok, username, retry, max_retries, running)

        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir.resolve()

        click.echo(f"🟢 @{username} is LIVE! Downloading until stream ends...")
        click.echo(f"   📁 → {out_path}")
        if uploader.is_configured():
            click.echo("   📤 Telegram upload enabled\n")
        else:
            click.echo("   💡 Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to auto-upload\n")

        seg_sec = segment * 60
        n, nbytes = service.download_until_ends(username, out_dir, seg_sec, running)

        if n > 0:
            click.echo(f"\n✅ Downloaded {n} segments  ({nbytes / 1024 / 1024:.1f} MB)")
        else:
            click.echo("\n⚠️  No data received.")
            sys.exit(1)
    finally:
        signal.signal(signal.SIGINT, original_handler)


@cli.command()
@click.argument("username")
@click.option("-o", "--output", default="./output", help="Output directory (default: ./output)")
@click.option("-s", "--segment", default=1, type=int, help="Segment length in minutes (default: 1)")
@click.option(
    "-r",
    "--retry",
    default=300,
    type=int,
    help="Seconds between checks when offline (default: 300)",
)
def monitor(username: str, output: str, segment: int, retry: int) -> None:
    """Monitor 24/7 — check every 5 min, auto-download when user goes live.

    Downloads until the stream ends, then waits and checks again.
    """
    # Check user exists before starting 24/7 monitoring
    tiktok = TikTokClient()
    exists = tiktok.user_exists(username)
    if exists is False:
        click.echo(f"🔴 @{username} does not exist on TikTok.")
        sys.exit(1)
    elif exists is None:
        click.echo("🟡 Could not verify user — TikTok challenge page. Continuing anyway...")

    service = MonitorService()
    try:
        service.run(
            username=username,
            output_dir=output,
            segment_minutes=segment,
            retry_seconds=retry,
        )
    except KeyboardInterrupt:
        sys.exit(0)


def _wait_for_live(
    tiktok: TikTokClient,
    username: str,
    retry: int,
    max_retries: int,
    running: list[bool],
) -> StreamInfo:
    """Poll TikTok until the user goes live or max_retries exhausted.

    Args:
        tiktok: TikTok client for live checks.
        username: TikTok username (without @).
        retry: Seconds between checks.
        max_retries: Number of checks before giving up.
        running: Shared mutable flag; set ``[False]`` to abort.

    Returns:
        A StreamInfo with a valid stream URL.

    Raises:
        SystemExit: If max_retries exhausted or user pressed Ctrl+C.
    """
    for attempt in range(1, max_retries + 1):
        if not running[0]:
            sys.exit(1)
        info = tiktok.get_stream_info(username)
        if info and info.best_url():
            return info
        click.echo(f"🟡 @{username} appears offline (attempt {attempt}/{max_retries})")
        for _ in range(retry):
            if not running[0]:
                break
            time.sleep(1)

    click.echo(f"🔴 @{username} is not live after {max_retries} attempts.")
    sys.exit(1)


def main() -> None:
    """Entry point for ``python -m tokstash`` and the installed CLI."""
    cli()
