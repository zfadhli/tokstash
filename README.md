# tokstash

Download and stash TikTok livestreams in 1-minute playable segments.
Uploads directly to Telegram to save disk space.

## Features

- **Auto-monitor**: Watches for streams 24/7 — starts downloading when the user goes live, waits and retries when offline
- **1-minute segments**: Short playable chunks instead of one giant file (safer, no corruption from interrupted downloads)
- **Stall detection**: If the stream freezes for 15 seconds, the segment is cut short and the script checks if the stream ended
- **Graceful Ctrl+C**: Press Ctrl+C mid-download — the partial segment is remuxed to MP4 and uploaded to Telegram
- **Short stream support**: Even a 7-second clip gets uploaded — no more "No data received" for brief streams
- **Telegram upload**: Uploads completed segments as playable videos to Telegram, deletes local files (free cloud storage)
- **Concurrent uploads**: Upload runs in the background while the next segment downloads — no waiting
- **Upload retries**: Failed uploads retry up to 3 times with exponential backoff (2s, 4s, 8s)
- **WAF bypass**: Uses `curl_cffi` with Chrome TLS impersonation to get past TikTok's bot detection
- **Webcast verification**: Cross-checks room IDs against TikTok's Webcast API — eliminates stale-room false positives
- **User existence check**: Rejects typos/non-existent usernames instantly instead of retrying
- **Fresh URLs**: New stream URL fetched before each segment — handles URL expiration

## Requirements

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) (must be in PATH — `ffmpeg -version`)
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)
- A Telegram bot (optional, for cloud storage)

## Installation

```bash
git clone <repo-url> tokstash
cd tokstash
uv sync
```

## Usage

### Quick download — stream ends, script stops

```bash
uv run tokstash download <username>
```

Checks every 10 seconds. Retries up to 5 times, then gives up.

### Auto-monitor — runs forever, downloads whenever live

```bash
uv run tokstash monitor <username>
```

Checks every 5 minutes when offline. When the user goes live, starts downloading
automatically. When the stream ends, waits and checks again. Press Ctrl+C to stop.

### Options

| Command | Flag | Default | Description |
|---------|------|---------|-------------|
| both | `-o, --output` | `./output` | Where to save segments |
| both | `-s, --segment` | `1` | Segment length in minutes |
| `download` | `-r, --retry` | `10` | Seconds between checks when offline |
| `download` | `-m, --max-retries` | `5` | Max offline checks before giving up |
| `monitor` | `-r, --retry` | `300` | Seconds between checks when offline |

```bash
# Monitor with custom check interval
uv run tokstash monitor noxknalpotracing1 -o ./recordings -s 2 -r 60

# Download, check every 30s, give up after 20 tries
uv run tokstash download noxknalpotracing1 -r 30 -m 20
```

## Release Process

This project uses [python-semantic-release](https://python-semantic-release.readthedocs.io/)
to automate versioning based on [Conventional Commits](https://www.conventionalcommits.org/).

### Bumping the version

After merging changes to `main`, run:

```bash
export GH_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"  # GitHub personal access token
uv run semantic-release version
```

This will:
1. Parse commits since the last tag
2. Determine the next version (`fix:` → patch, `feat:` → minor, `BREAKING CHANGE` → major)
3. Update `pyproject.toml` version
4. Generate `CHANGELOG.md`
5. Create a git tag
6. Push commit + tag to GitHub
7. Create a GitHub release

| Commit type | Bump | Example |
|-------------|------|---------|
| `fix:` | patch | `0.0.5` → `0.0.6` |
| `feat:` | minor | `0.0.5` → `0.1.0` |
| `BREAKING CHANGE:` | major | `0.0.5` → `1.0.0` |
| `docs:` / `test:` / `chore:` / `refactor:` | no bump | — |

### Preview without applying

```bash
uv run semantic-release version --print
```

### Skip GitHub release creation

```bash
uv run semantic-release version --no-vcs-release
```

### Getting a GitHub token

1. Go to https://github.com/settings/tokens
2. **Generate new token → Tokens (classic)**
3. Scope: **`repo`**
4. Set as `GH_TOKEN` environment variable

## Telegram Upload (Optional)

### 1. Create a bot

Open Telegram, search for [@BotFather](https://t.me/BotFather), send:

```
/newbot
```

Follow the prompts. You'll receive a token like `1234567890:ABCdefGHIjkl...`.

### 2. Get your chat ID

Message [@userinfobot](https://t.me/userinfobot) — it replies with your numeric chat ID instantly.

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjkl-mnoPQRstuvWXyz"
TELEGRAM_CHAT_ID="123456789"
```

Now segments will auto-upload to Telegram and be deleted from disk.

### Increase upload limit (optional, 50 MB default)

The Telegram Bot API limits file uploads to **50 MB**. If your segments exceed this:

1. In Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/setuploadsize` → select your bot → enter `2000000000` (2 GB max)
3. No code changes needed — the tool will use whatever limit BotFather allows

### Verify it works

```bash
uv run python -c "
from tokstash.infrastructure.telegram import TelegramUploader
u = TelegramUploader()
print('✅ Configured' if u.is_configured() else '❌ Missing env vars')
"
```

## Output

```
📡 Monitoring @noxknalpotracing1 for livestreams
   📤 Telegram upload enabled — files deleted after upload
   Press Ctrl+C to stop

🟢 @noxknalpotracing1 is LIVE!

  [noxknalpotracing1 20260515_143012.ts]  (0:42)
       💾 1.2 MB
       📤 Telegram: ✅
  [noxknalpotracing1 20260515_143112.ts]  (1:00)
       💾 1.3 MB
       📤 Telegram: ✅
🟡 Stream ended. Checking again in 3 min...
```

Segments are sent to Telegram as playable MP4 videos (remuxed from TS — no re-encoding).

## Project Structure

```
src/tokstash/
├── __init__.py
├── __main__.py               # python -m tokstash entry
├── cli.py                    # CLI commands (click)
├── models/
│   └── stream.py             # StreamInfo data model
├── infrastructure/
│   ├── tiktok_client.py      # TikTok live detection (curl_cffi + Webcast API)
│   ├── telegram.py           # Telegram upload (python-telegram-bot)
│   └── ffmpeg.py             # ffmpeg segment download + stall detection
└── services/
    └── monitor.py            # auto-monitor loop + concurrent uploads
```

## How It Works

1. **Live check**: Fetches the TikTok live page with `curl_cffi` impersonating Chrome 120
   to bypass WAF. Extracts stream URLs (FLV HD, FLV LD, HLS) and `roomId` from the HTML.

2. **Webcast verification**: The `roomId` is cross-checked against TikTok's internal Webcast
   API (`webcast.tiktok.com/webcast/room/info/`). This is the definitive live check — the
   same API the browser uses. Eliminates false positives from stale rooms that the page HTML
   still advertises briefly after a stream ends.

3. **User existence check**: Non-existent accounts (typos, deleted users) are rejected
   immediately — no pointless retries.

4. **Download**: ffmpeg captures the FLV stream, saves as MPEG-TS (`.ts`) — a container
   designed for streaming that stays playable even if interrupted.

5. **Stall detection**: While ffmpeg runs, the script monitors the output file size every
   second. If it doesn't grow for 15 seconds, the stream likely ended — cuts the segment
   short instead of waiting the full minute.

6. **Short stream handling**: If a stream ends mid-download, the partial segment is kept
   and uploaded — even if it's only a few seconds long or under 1 MB.

7. **Graceful Ctrl+C**: Press Ctrl+C during a download. The current segment finishes
   immediately, gets remuxed to MP4, and uploaded to Telegram before the script exits.

8. **Remux**: Completed `.ts` segment is quickly remuxed to `.mp4` (`ffmpeg -c copy`,
   no re-encoding, takes ~1 second).

9. **Upload**: `.mp4` is uploaded to Telegram via python-telegram-bot, then both
   `.ts` and `.mp4` are deleted from disk. Upload runs in a background thread so the
   next segment starts downloading immediately. Failed uploads retry 3 times.

10. **Monitor loop**: When the stream ends, the script waits 3 minutes, then checks
    again. If the user starts streaming again, it resumes automatically.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "does not exist on TikTok" for a real account | Rare WAF challenge — just retry. The check retries 3 times automatically |
| "LIVE!" but download fails immediately | Stream URL expired between page load and ffmpeg start. The Webcast API prevents most of these, but race conditions can still happen |
| Telegram upload fails with "Request Entity Too Large" | Increase the limit via BotFather `/setuploadsize` (max 2000 MB) |
| Telegram upload fails for other reasons | Check `.env` values, run `uv run python -c "from tokstash.infrastructure.telegram import TelegramUploader; print(TelegramUploader().is_configured())"` |
| ffmpeg not found | Install ffmpeg: `sudo apt install ffmpeg` or `brew install ffmpeg` |
| `tokstash: command not found` | Run via `uv run tokstash ...` |
| Segments still show `_part001` | Run `uv sync --reinstall` to update installed scripts |
