"""CLI interface for tokstash — download and monitor TikTok livestreams.

Provides two commands via click:

- ``download``: Single-session download until the stream ends.
- ``monitor``: Persistent 24/7 monitoring with auto-download.
"""

import os
import sys
from pathlib import Path

import click

from tokstash.monitor import run_download, run_monitor
from tokstash.uploader import is_configured

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
    from tokstash.live_check import get_stream_url

    out_dir = output

    for attempt in range(MAX_RETRIES):
        info = get_stream_url(username)
        if info and info.flv_hd:
            break
        click.echo(f"🟡 @{username} appears offline (attempt {attempt + 1}/{MAX_RETRIES})")
        import time

        time.sleep(RETRY_DELAY)
    else:
        click.echo(f"🔴 @{username} is not live after {MAX_RETRIES} attempts.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.abspath(out_dir)

    click.echo(f"🟢 @{username} is LIVE! Downloading until stream ends...")
    click.echo(f"   📁 → {out_path}")
    if is_configured():
        click.echo("   📤 Telegram upload enabled\n")
    else:
        click.echo("   💡 Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to auto-upload\n")

    seg_sec = segment * 60
    n, nbytes = run_download(username, Path(out_dir), seg_sec)

    if n > 0:
        click.echo(f"\n✅ Downloaded {n} segments  ({nbytes / 1024 / 1024:.1f} MB)")
    else:
        click.echo("\n⚠️  No data received.")
        sys.exit(1)


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
    try:
        run_monitor(
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
