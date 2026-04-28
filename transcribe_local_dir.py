import os
import re
import sys
from pathlib import Path

from faster_whisper import WhisperModel


MEDIA_EXTENSIONS = {
    ".aac",
    ".flac",
    ".flv",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".wav",
    ".webm",
}
PUNCTUATION_BREAKS = {"。", "？", "！", "!", "?"}


def safe_name(name: str) -> str:
    name = re.sub(r"[/:*?\"<>|]", "_", name)
    return name.strip() or "transcript"


def collect_media_files(input_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(input_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
    ]


def format_segments(segments) -> str:
    paragraphs: list[str] = []
    current: list[str] = []

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        current.append(text)
        if text[-1] in PUNCTUATION_BREAKS or len(" ".join(current)) >= 220:
            paragraphs.append(" ".join(current))
            current = []

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs).strip()


def write_transcript(output_path: Path, source_path: Path, transcript: str) -> None:
    output_path.write_text(
        f"# {source_path.stem}\n\n"
        f"**Source file:** {source_path}\n\n"
        "---\n\n"
        f"{transcript}\n",
        encoding="utf-8",
    )


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python transcribe_local_dir.py <media_dir> [output_dir]")
        return 2

    input_dir = Path(sys.argv[1]).expanduser()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input directory not found: {input_dir}")
        return 2

    output_dir = (
        Path(sys.argv[2]).expanduser()
        if len(sys.argv) >= 3
        else Path("local_transcripts") / input_dir.name
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    files = collect_media_files(input_dir)
    if not files:
        print(f"No media files found in {input_dir}")
        return 1

    model_name = os.getenv("BILI_ASR_MODEL", "medium")
    language = os.getenv("BILI_ASR_LANGUAGE", "zh")
    compute_type = os.getenv("BILI_ASR_COMPUTE_TYPE", "int8")
    device = os.getenv("BILI_ASR_DEVICE", "cpu")

    print(f"Input: {input_dir}", flush=True)
    print(f"Output: {output_dir}", flush=True)
    print(
        f"Loading faster-whisper model={model_name}, "
        f"language={language}, device={device}, compute_type={compute_type}",
        flush=True,
    )
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    for index, media_path in enumerate(files, start=1):
        output_path = output_dir / f"{safe_name(media_path.stem)}.md"
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"[{index}/{len(files)}] Skipping existing: {output_path.name}", flush=True)
            continue

        print(f"[{index}/{len(files)}] Transcribing: {media_path.name}", flush=True)
        segments, info = model.transcribe(
            str(media_path),
            language=language,
            vad_filter=True,
        )
        transcript = format_segments(segments)
        write_transcript(output_path, media_path, transcript)
        print(
            f"[{index}/{len(files)}] Saved: {output_path.name} "
            f"({len(transcript)} chars, detected={info.language})",
            flush=True,
        )

    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
