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
from tokstash.services.monitor import MonitorService

MAX_RETRIES = 5
"""int: Number of times to retry live check before reporting offline."""
RETRY_DELAY = 10
"""int: Seconds between live check retries."""


@click.group()
def cli() -> None:
    """Download TikTok livestreams in playable segments."""


@cli.command()
@click.argument("username")
@click.option("-o", "--output", default="./output", help="Output directory (default: ./output)")
@click.option("-s", "--segment", default=1, type=int, help="Segment length in minutes (default: 1)")
def download(username: str, output: str, segment: int) -> None:
    """Download livestream until the user goes offline, then stop."""
    tiktok = TikTokClient()
    uploader = TelegramUploader()
    service = MonitorService(tiktok_client=tiktok, uploader=uploader)
    out_dir = Path(output)

    # Check user exists before attempting download
    if not tiktok.user_exists(username):
        click.echo(f"🔴 @{username} does not exist on TikTok.")
        sys.exit(1)

    running: list[bool] = [True]

    def handle_sigint(*_args: object) -> None:
        """Signal handler: gracefully stop downloads on Ctrl+C."""
        running[0] = False
        click.echo("\n⏹️  Stopping...")

    original_handler = signal.signal(signal.SIGINT, handle_sigint)

    try:
        for attempt in range(MAX_RETRIES):
            info = tiktok.get_stream_info(username)
            if info and info.best_url():
                break
            click.echo(f"🟡 @{username} appears offline (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(RETRY_DELAY)
        else:
            click.echo(f"🔴 @{username} is not live after {MAX_RETRIES} attempts.")
            sys.exit(1)

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
    if not tiktok.user_exists(username):
        click.echo(f"🔴 @{username} does not exist on TikTok.")
        sys.exit(1)

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


def main() -> None:
    """Entry point for ``python -m tokstash`` and the installed CLI."""
    cli()
