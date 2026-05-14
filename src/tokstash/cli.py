"""CLI interface for tokstash."""

import os
import sys

import click

from tokstash.monitor import run_download, run_monitor
from tokstash.uploader import is_configured


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

    # Retry up to 5 times (10s apart) before concluding offline
    info = get_stream_url(username)
    for attempt in range(5):
        if info and info.flv_hd:
            break
        click.echo(f"🟡 @{username} appears offline (attempt {attempt + 1}/5)")
        import time

        time.sleep(10)
        info = get_stream_url(username)
    else:
        click.echo(f"🔴 @{username} is not live after 5 attempts.")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.abspath(out_dir)

    click.echo(f"🟢 @{username} is LIVE! Downloading until stream ends...")
    click.echo(f"   📁 → {out_path}")
    if is_configured():
        click.echo("   📤 Telegram upload enabled\n")
    else:
        click.echo("   💡 Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID to auto-upload\n")

    from pathlib import Path

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
    cli()
