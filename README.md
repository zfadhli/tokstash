# tokstash

Download and stash TikTok livestreams in 1-minute playable segments.
Uploads directly to Telegram to save disk space.

## Features

- **Auto-monitor**: Watches for streams 24/7 — starts downloading when the user goes live, waits and retries when offline
- **1-minute segments**: Short playable chunks instead of one giant file (safer, no corruption from interrupted downloads)
- **Stall detection**: If the stream freezes for 15 seconds, the segment is cut short and the script checks if the stream ended
- **Telegram upload**: Uploads completed segments as playable videos to Telegram, deletes local files (free cloud storage)
- **Concurrent uploads**: Upload runs in the background while the next segment downloads — no waiting
- **Upload retries**: Failed uploads retry up to 3 times with exponential backoff (2s, 4s, 8s)
- **WAF bypass**: Uses `curl_cffi` with Chrome TLS impersonation to get past TikTok's bot detection
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

Downloads 1-minute segments until the stream ends, then exits.

### Auto-monitor — runs forever, downloads whenever live

```bash
uv run tokstash monitor <username>
```

Checks every 3 minutes when offline. When the user goes live, starts downloading
automatically. When the stream ends, waits and checks again. Press Ctrl+C to stop.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `./output` | Where to save segments |
| `-s, --segment` | `1` | Segment length in minutes |
| `-r, --retry` | `300` | Seconds between checks when offline (monitor only) |

```bash
uv run tokstash monitor noxknalpotracing1 -o ./recordings -s 2 -r 60
```

## Private / Followers-Only Livestreams

To access private, age-restricted, or followers-only livestreams, you need
to provide TikTok session cookies from a logged-in account.

### Getting cookies

1. Open **TikTok.com** in your browser and log in
2. Open DevTools:
   - **Chrome/Edge:** `F12` → **Application** tab → **Cookies** → `www.tiktok.com`
   - **Firefox:** `F12` → **Storage** tab → **Cookies** → `www.tiktok.com`
3. Copy the `sessionid` cookie value (the main auth cookie)

### Configure

Add to `.env`:

```env
TIKTOK_COOKIES="sessionid=abc123; tt_chain_token=def456"
```

`sessionid` is the minimum required. `tt_chain_token` and `msToken` can
also be included for extra auth coverage.

### Verify

```bash
uv run python -c "
from tokstash.infrastructure.tiktok_client import TikTokClient
client = TikTokClient()
info = client.get_stream_info('username')
if info:
    print(f'✅ Room {info.room_id} - FLV HD: {bool(info.flv_hd)}')
else:
    print('❌ Not live or cookies invalid')
"
```

If cookies are missing or invalid, behavior falls back to public-only
streams (identical to before).

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
│   ├── tiktok_client.py      # TikTok live detection (curl_cffi)
│   ├── telegram.py           # Telegram upload (python-telegram-bot)
│   └── ffmpeg.py             # ffmpeg segment download + stall detection
└── services/
    └── monitor.py            # auto-monitor loop + concurrent uploads
```

## How It Works

1. **Live check**: Fetches the TikTok live page with `curl_cffi` impersonating Chrome 120
   to bypass WAF. Extracts stream URLs (FLV HD, FLV LD, HLS) and room metadata from the HTML.

2. **Download**: ffmpeg captures the FLV stream, saves as MPEG-TS (`.ts`) — a container
   designed for streaming that stays playable even if interrupted.

3. **Stall detection**: While ffmpeg runs, the script monitors the output file size every
   second. If it doesn't grow for 15 seconds, the stream likely ended — cuts the segment
   short instead of waiting the full minute.

4. **Remux**: Completed `.ts` segment is quickly remuxed to `.mp4` (`ffmpeg -c copy`,
   no re-encoding, takes ~1 second).

5. **Upload**: `.mp4` is uploaded to Telegram via python-telegram-bot, then both
   `.ts` and `.mp4` are deleted from disk. Upload runs in a background thread so the
   next segment starts downloading immediately. Failed uploads retry 3 times.

6. **Monitor loop**: When the stream ends, the script waits 3 minutes, then checks
   again. If the user starts streaming again, it resumes automatically.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "User is not live" when they are | TikTok WAF may have changed — try `uv sync --reinstall` |
| Telegram upload fails | Check `.env` values, run `uv run python -c "from tokstash.infrastructure.telegram import TelegramUploader; print(TelegramUploader().is_configured())"` |
| ffmpeg not found | Install ffmpeg: `sudo apt install ffmpeg` or `brew install ffmpeg` |
| `tokstash: command not found` | Run via `uv run tokstash ...` |
| Segments still show `_part001` | Run `uv sync --reinstall` to update installed scripts |
