# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

A local CLI toolset that converts Bilibili (and, experimentally, Douyin) videos into Markdown transcripts/articles. Bilibili is the primary, well-supported path: it prefers official subtitles and falls back to local `faster-whisper` ASR. Douyin has no official subtitle API worth relying on, so it's ASR-only via `yt-dlp`.

## Setup

Python 3.12 is required (ASR deps don't reliably have wheels on newer versions).

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r requirements.txt
```

## Core commands

```bash
# Bilibili: subtitle-first, ASR fallback
python convert.py "https://www.bilibili.com/video/BV1hvSKB4EgK/"
python convert.py "BV1hvSKB4EgK"                       # bare BV id
python convert.py "https://www.bilibili.com/video/<BV_ID>/?p=2"  # specific page

# Bilibili login (QR scan), writes cookies to .env
python refresh_env.py

# Douyin: ASR-only, needs a cookies.txt (see README)
python convert_douyin.py "https://v.douyin.com/xxxxxxxx/" --cookies douyin_cookies.txt

# Batch-transcribe a folder of already-downloaded media files
python transcribe_local_dir.py "/path/to/video-folder" "local_transcripts/output-folder"
```

No test suite exists. Verify changes by actually running the relevant script against a real video/BV id.

## Architecture

- `convert.py` — Bilibili pipeline. Talks to `bilibili_api`, tries official subtitles first (`fetch_official_transcript`), falls back to downloading the media stream and calling `transcribe_with_local_asr`. Also owns `TranscriptError`, credential loading/refresh (`prepare_credential`, `save_credential`), and preview-stream detection (`assert_media_covers_expected_duration` — Bilibili sometimes silently returns a short preview instead of the full video for restricted content; this guards against generating a misleadingly "complete" transcript from it).
- `convert_douyin.py` — Douyin pipeline. Uses `yt_dlp`'s Python API to resolve/download media, then imports and reuses `transcribe_with_local_asr`/`TranscriptError` from `convert.py` rather than duplicating ASR logic. Douyin's web API has an intermittent anti-bot check even with valid cookies, so downloads are retried a few times before giving up.
- `transcribe_local_dir.py` — standalone batch ASR over a directory of local media files; has its own copy of the segment-formatting/transcription logic (not shared with `convert.py` — predates `convert_douyin.py`'s reuse pattern).
- `refresh_env.py` — interactive QR login flow that writes Bilibili session cookies into `.env`.
- `douyin_cookies_from_devtools.py` — converts a cookie table pasted from browser DevTools (Application → Cookies) into a Netscape `cookies.txt`. Kept as an explicit opt-in tool, not the default — see the credentials note below for why it doesn't reliably work for Douyin.

## Conventions

- Output files: `article_<bvid>.md` (Bilibili), `article_douyin_<video_id>.md` (Douyin). Both are git-ignored (`article_*.md` in `.gitignore`), along with downloaded media and `local_transcripts/`.
- ASR tuning via env vars (`.env` or shell): `BILI_ASR_MODEL` (default `medium`), `BILI_ASR_LANGUAGE` (default `zh`), `BILI_ASR_DEVICE`, `BILI_ASR_COMPUTE_TYPE`, `BILI_ASR_CACHE_DIR`. These are shared across both pipelines despite the `BILI_` prefix (historical naming from before Douyin support existed).
- Downloaded media is treated as a disposable cache — scripts skip re-downloading if the file already exists, and it's fine to delete it after a successful transcript.

## Credentials — two very different trust models

- **Bilibili**: session cookies live in `.env` (git-ignored), refreshed via `refresh_env.py`'s QR flow or auto-refreshed by `prepare_credential()`. Straightforward, long-lived, no browser access needed at runtime.
- **Douyin**: `convert_douyin.py` defaults to `--cookies-from-browser chrome` (a `yt-dlp` passthrough). This was not the first choice — a narrowly-scoped `cookies.txt` file (see `douyin_cookies_from_devtools.py`) was tried first and rejected after live testing: Douyin's anti-bot check depends on `msToken`, a token the page's JS keeps rotating while a tab is open, so any static file export is missing it and reliably fails (confirmed via side-by-side testing — file: 0/3 successes, live browser: 3/3, at the same moment against the same video). `--cookies-from-browser` reads Chrome's cookie store live, so it has the current `msToken`. The tradeoff is real and was made deliberately, not by default: on macOS this triggers a "Chrome Safe Storage" Keychain prompt, and choosing "Always Allow" grants silent, standing decryption access to Chrome's *entire* cookie store (every site, not just Douyin). `--cookies <file>` is still supported as an explicit opt-in for cases where it might be sufficient (e.g. a site without a rotating token), but don't present it as the reliable default for Douyin — it isn't.

## Stray files

`check_auth.py`, `check_qr.py`, `debug_auth.py`, `try_refresh.py` at the repo root are untracked ad hoc debugging scripts from earlier Bilibili auth troubleshooting, superseded by `refresh_env.py`. They're not part of the documented workflow — don't build on them without checking with the user first.
