# bilibili2article

Fetch or generate transcripts from Bilibili videos and save them as Markdown.

The tool tries Bilibili's official subtitle API first. If a video does not expose subtitles, it can download the playable media stream and run local ASR with `faster-whisper`.

## Setup

Use Python 3.12 for the ASR environment. Some speech/ML wheels may not be available on newer Python versions.

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r requirements.txt
```

If you do not have `python3.12`, install it with your preferred Python manager first.

## Login

Some Bilibili videos and subtitle metadata require a logged-in session.

```bash
source .venv312/bin/activate
python refresh_env.py
```

Scan the QR code with the Bilibili app. This writes cookies to `.env`, which is ignored by git.

`.env.example` lists the supported cookie and ASR environment variables.

## Convert A Bilibili Video

```bash
source .venv312/bin/activate
python convert.py "https://www.bilibili.com/video/BV1hvSKB4EgK/"
```

Output is written to:

```text
article_<bvid>.md
```

For a specific multi-page video page:

```bash
python convert.py "https://www.bilibili.com/video/<BV_ID>/?p=2"
```

## Local ASR Options

By default, fallback ASR uses:

- model: `medium`
- language: `zh`
- device: `cpu`
- compute type: `int8`

Override model/language/cache path with environment variables:

```bash
BILI_ASR_MODEL=small BILI_ASR_LANGUAGE=zh python convert.py "<bilibili-url>"
```

```bash
BILI_ASR_CACHE_DIR=./asr_cache python convert.py "<bilibili-url>"
```

Downloaded media is only a cache. It can be deleted after transcription.

## Transcribe Local Video Files

Transcribe one local file:

```bash
source .venv312/bin/activate

.venv312/bin/python - <<'PY'
from pathlib import Path
from convert import transcribe_with_local_asr

video = Path("/full/path/to/video.mp4")
out = Path("local_transcripts") / f"{video.stem}.md"
out.parent.mkdir(exist_ok=True)

text = transcribe_with_local_asr(video)
out.write_text(
    f"# {video.stem}\n\n**Source file:** {video}\n\n---\n\n{text}\n",
    encoding="utf-8",
)
print(f"Saved: {out}")
PY
```

Transcribe every media file in a directory:

```bash
source .venv312/bin/activate
python transcribe_local_dir.py "/path/to/video-folder" "local_transcripts/output-folder"
```

Run a long batch in the background:

```bash
nohup env BILI_ASR_MODEL=medium BILI_ASR_LANGUAGE=zh \
  .venv312/bin/python transcribe_local_dir.py \
  "/path/to/video-folder" \
  "local_transcripts/output-folder" \
  > transcribe.log 2>&1 &
```

Watch progress:

```bash
tail -f transcribe.log
```

The batch script skips existing transcript files, so rerunning the same command resumes incomplete batches.

## Access Notes

If Bilibili only authorizes a preview stream, the script will stop instead of producing a misleading partial transcript. For UPOWER/charging-exclusive videos, the logged-in account must be able to play the full video.

This project does not bypass Bilibili access controls. It only uses media/subtitle streams available to the current logged-in session.
