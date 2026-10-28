# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

A local CLI toolset that converts Bilibili videos into Markdown transcripts/articles. It prefers official subtitles and falls back to local `faster-whisper` ASR. Other platforms are out of scope: the README points users to 豆包 for Douyin and 点点 for Xiaohongshu instead (Douyin support was tried and removed).

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

# Batch-transcribe a folder of already-downloaded media files
python transcribe_local_dir.py "/path/to/video-folder" "local_transcripts/output-folder"
```

No test suite exists. Verify changes by actually running the relevant script against a real video/BV id.

## Architecture

- `convert.py` — Bilibili pipeline. Talks to `bilibili_api`, tries official subtitles first (`fetch_official_transcript`), falls back to downloading the media stream and calling `transcribe_with_local_asr`. Also owns `TranscriptError`, credential loading/refresh (`prepare_credential`, `save_credential`), and preview-stream detection (`assert_media_covers_expected_duration` — Bilibili sometimes silently returns a short preview instead of the full video for restricted content; this guards against generating a misleadingly "complete" transcript from it).
- `transcribe_local_dir.py` — standalone batch ASR over a directory of local media files; has its own copy of the segment-formatting/transcription logic (not shared with `convert.py`).
- `refresh_env.py` — interactive QR login flow that writes Bilibili session cookies into `.env`.

## Conventions

- Output files: `article_<bvid>.md`, git-ignored (`article_*.md` in `.gitignore`), along with downloaded media and `local_transcripts/`.
- ASR tuning via env vars (`.env` or shell): `BILI_ASR_MODEL` (default `medium`), `BILI_ASR_LANGUAGE` (default `zh`), `BILI_ASR_DEVICE`, `BILI_ASR_COMPUTE_TYPE`, `BILI_ASR_CACHE_DIR`.
- Downloaded media is treated as a disposable cache — scripts skip re-downloading if the file already exists, and it's fine to delete it after a successful transcript.

## Credentials

Bilibili session cookies live in `.env` (git-ignored), refreshed via `refresh_env.py`'s QR flow or auto-refreshed by `prepare_credential()`.

## Stray files

`check_auth.py`, `check_qr.py`, `debug_auth.py`, `try_refresh.py` at the repo root are untracked ad hoc debugging scripts from earlier Bilibili auth troubleshooting, superseded by `refresh_env.py`. They're not part of the documented workflow — don't build on them without checking with the user first.
