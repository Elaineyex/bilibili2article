import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bilibili_api import Credential, video
from bilibili_api.video import (
    AudioStreamDownloadURL,
    VideoDownloadURLDataDetecter,
)
from dotenv import load_dotenv, set_key


load_dotenv(".env")

DEFAULT_BVID = "BV1keFjzPE6u"
BVID_RE = re.compile(r"BV[a-zA-Z0-9]+")
PUNCTUATION_BREAKS = {"。", "？", "！", "!", "?"}
MEDIA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}


class TranscriptError(RuntimeError):
    pass


class PreviewOnlyError(TranscriptError):
    pass


def parse_video_input(raw_input: str) -> tuple[str, int | None]:
    match = BVID_RE.search(raw_input)
    bvid = match.group(0) if match else raw_input.strip()

    page = None
    parsed = urlparse(raw_input)
    if parsed.query:
        page_values = parse_qs(parsed.query).get("p")
        if page_values:
            try:
                page = max(1, int(page_values[0]))
            except ValueError:
                page = None

    return bvid, page


def build_credential() -> Credential:
    return Credential(
        sessdata=os.getenv("SESSDATA"),
        bili_jct=os.getenv("BILI_JCT"),
        buvid3=os.getenv("BUVID3"),
        buvid4=os.getenv("BUVID4"),
        dedeuserid=os.getenv("DEDEUSERID"),
        ac_time_value=os.getenv("AC_TIME_VALUE"),
    )


def refresh_fields_available() -> bool:
    return all(
        os.getenv(key)
        for key in (
            "SESSDATA",
            "BILI_JCT",
            "BUVID3",
            "BUVID4",
            "DEDEUSERID",
            "AC_TIME_VALUE",
        )
    )


async def prepare_credential() -> Credential:
    credential = build_credential()

    try:
        is_valid = await credential.check_valid()
    except Exception as exc:
        print(f"Warning: Could not check Bilibili login status: {exc}")
        is_valid = False

    if not is_valid:
        print("Warning: Credentials missing or invalid. Some videos may be inaccessible.")
        print("Please run 'python3 refresh_env.py' to login again if fetching fails.")
        if not os.getenv("SESSDATA"):
            return Credential()
        return credential

    if not refresh_fields_available():
        print(
            "Warning: Login is valid, but some silent-refresh fields are missing. "
            "This only affects future cookie refresh, not current video access."
        )
        return credential

    try:
        needs_refresh = await credential.check_refresh()
    except Exception as exc:
        print(f"Warning: Could not check cookie refresh state: {exc}")
        return credential

    if not needs_refresh:
        return credential

    try:
        print("Refreshing Bilibili cookies...")
        await credential.refresh()
        save_credential(credential)
        print("Cookie refresh complete.")
    except Exception as exc:
        print(f"Warning: Cookie refresh failed, continuing with current cookies: {exc}")

    return credential


def save_credential(credential: Credential) -> None:
    env_path = ".env"
    Path(env_path).touch(exist_ok=True)
    values = {
        "SESSDATA": credential.sessdata,
        "BILI_JCT": credential.bili_jct,
        "BUVID3": credential.buvid3,
        "BUVID4": credential.buvid4,
        "DEDEUSERID": credential.dedeuserid,
        "AC_TIME_VALUE": credential.ac_time_value,
    }
    for key, value in values.items():
        if value:
            set_key(env_path, key, str(value))


def choose_pages(info: dict[str, Any], requested_page: int | None) -> list[dict[str, Any]]:
    pages = info.get("pages") or [
        {
            "cid": info["cid"],
            "page": 1,
            "part": info["title"],
            "duration": info.get("duration"),
        }
    ]

    if requested_page is None:
        return pages

    for page in pages:
        if page.get("page") == requested_page:
            return [page]

    raise TranscriptError(f"Page p={requested_page} was not found on this video.")


def select_subtitle(subtitles: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not subtitles:
        return None

    preferred_languages = ("zh-CN", "zh-Hans", "zh", "ai-zh")
    for lang in preferred_languages:
        for subtitle in subtitles:
            if subtitle.get("lan") == lang:
                return subtitle

    for subtitle in subtitles:
        if "zh" in str(subtitle.get("lan", "")).lower():
            return subtitle

    return subtitles[0]


async def fetch_official_transcript(
    bili_video: video.Video, cid: int
) -> tuple[str, str] | None:
    try:
        sub_info = await bili_video.get_subtitle(cid)
    except Exception as exc:
        print(f"Official subtitle lookup failed: {exc}")
        return None

    subtitles = sub_info.get("subtitles", [])
    target = select_subtitle(subtitles)
    if not target:
        return None

    sub_url = target["subtitle_url"]
    if not sub_url.startswith("http"):
        sub_url = "https:" + sub_url

    lang_name = target.get("lan_doc") or target.get("lan") or "selected"
    print(f"Downloading official {lang_name} transcript...")

    async with httpx.AsyncClient(headers=MEDIA_HEADERS, timeout=60) as client:
        response = await client.get(sub_url)
        response.raise_for_status()
        data = response.json()

    return format_subtitle_body(data.get("body", [])), "official subtitles"


def format_subtitle_body(body: list[dict[str, Any]]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []

    for item in body:
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        current.append(content)
        if content[-1] in PUNCTUATION_BREAKS:
            paragraphs.append(" ".join(current))
            current = []

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs).strip()


def get_cache_dir() -> Path:
    configured = os.getenv("BILI_ASR_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.cwd()


def stream_extension(stream: Any) -> str:
    if isinstance(stream, AudioStreamDownloadURL):
        return ".m4a"
    parsed = urlparse(getattr(stream, "url", ""))
    suffix = Path(parsed.path).suffix
    return suffix if suffix else ".mp4"


def choose_media_stream(download_data: dict[str, Any]) -> Any:
    detector = VideoDownloadURLDataDetecter(download_data)
    streams = detector.detect_all()
    for stream in streams:
        if isinstance(stream, AudioStreamDownloadURL):
            return stream

    best_streams = detector.detect_best_streams()
    for stream in best_streams:
        if stream is not None:
            return stream

    for stream in streams:
        if stream is not None:
            return stream

    raise TranscriptError("No downloadable media stream was found for ASR fallback.")


def get_media_duration_seconds(media_path: Path) -> float | None:
    try:
        import av
    except ImportError:
        return None

    try:
        with av.open(str(media_path)) as container:
            if container.duration is None:
                return None
            return float(container.duration / av.time_base)
    except Exception:
        return None


def assert_media_covers_expected_duration(
    media_path: Path,
    expected_duration: float | None,
    source_context: str,
) -> None:
    if not expected_duration or expected_duration < 300:
        return

    actual_duration = get_media_duration_seconds(media_path)
    if actual_duration is None:
        print("Warning: Could not verify downloaded media duration before ASR.")
        return

    if actual_duration >= expected_duration * 0.8:
        return

    raise PreviewOnlyError(
        "Bilibili only provided a short playable media stream for ASR "
        f"({actual_duration:.0f}s downloaded vs {expected_duration:.0f}s expected). "
        f"{source_context}"
    )


def declared_stream_duration_seconds(download_data: dict[str, Any]) -> float | None:
    durl_items = download_data.get("durl") or []
    durations = [
        item.get("length") / 1000
        for item in durl_items
        if isinstance(item.get("length"), (int, float))
    ]
    if durations:
        return max(durations)
    return None


def assert_declared_stream_covers_expected_duration(
    download_data: dict[str, Any],
    expected_duration: float | None,
    source_context: str,
) -> None:
    if not expected_duration or expected_duration < 300:
        return

    declared_duration = declared_stream_duration_seconds(download_data)
    if declared_duration is None:
        return

    if declared_duration >= expected_duration * 0.8:
        return

    raise PreviewOnlyError(
        "Bilibili only declared a short playable media stream for ASR "
        f"({declared_duration:.0f}s available vs {expected_duration:.0f}s expected). "
        f"{source_context}"
    )


def build_access_context(info: dict[str, Any]) -> str:
    if info.get("is_upower_exclusive") and not info.get("is_upower_play"):
        return (
            "This video is UPOWER/charging exclusive for the current Bilibili "
            "account, so the API appears to be returning only the preview. "
            "Use cookies from an account that can play the full video, then rerun "
            "'python3 refresh_env.py'."
        )
    return (
        "The selected stream is much shorter than the video. This usually means "
        "the current account only has preview access, or Bilibili returned a "
        "preview stream instead of the full media."
    )


async def download_media_for_asr(
    bili_video: video.Video,
    cid: int,
    bvid: str,
    page_number: int,
    expected_duration: float | None,
    source_context: str,
) -> Path:
    download_data = await bili_video.get_download_url(cid=cid)
    assert_declared_stream_covers_expected_duration(
        download_data,
        expected_duration,
        source_context,
    )
    stream = choose_media_stream(download_data)
    url = getattr(stream, "url", None)
    if not url:
        raise TranscriptError("The selected media stream did not include a URL.")

    cache_dir = get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    media_path = cache_dir / f"{bvid}_p{page_number}{stream_extension(stream)}"

    if media_path.exists() and media_path.stat().st_size > 0:
        print(f"Using cached media: {media_path}")
        try:
            assert_media_covers_expected_duration(
                media_path,
                expected_duration,
                source_context,
            )
        except PreviewOnlyError:
            print("Cached media is only a preview; deleting it before retrying.")
            media_path.unlink(missing_ok=True)
        else:
            return media_path

    if media_path.exists() and media_path.stat().st_size > 0:
        return media_path

    print("Downloading media for local ASR...")
    tmp_path = media_path.with_suffix(media_path.suffix + ".part")
    async with httpx.AsyncClient(headers=MEDIA_HEADERS, timeout=None) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    if chunk:
                        file.write(chunk)

    tmp_path.replace(media_path)
    assert_media_covers_expected_duration(
        media_path,
        expected_duration,
        source_context,
    )
    return media_path


def transcribe_with_local_asr(media_path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptError(
            "Official subtitles were unavailable and local ASR is not installed. "
            "Create/use a Python 3.12 environment, then run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    model_name = os.getenv("BILI_ASR_MODEL", "medium")
    language = os.getenv("BILI_ASR_LANGUAGE", "zh")

    print(
        f"Transcribing locally with faster-whisper "
        f"(model={model_name}, language={language}, compute_type=int8)..."
    )
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(media_path),
        language=language,
        vad_filter=True,
    )

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

    transcript = "\n\n".join(paragraphs).strip()
    if not transcript:
        raise TranscriptError("Local ASR completed but produced an empty transcript.")
    return transcript


async def fetch_asr_transcript(
    bili_video: video.Video,
    cid: int,
    bvid: str,
    page_number: int,
    expected_duration: float | None,
    source_context: str,
) -> tuple[str, str]:
    media_path = await download_media_for_asr(
        bili_video,
        cid,
        bvid,
        page_number,
        expected_duration,
        source_context,
    )
    transcript = await asyncio.to_thread(transcribe_with_local_asr, media_path)
    return transcript, "local ASR"


async def fetch_page_transcript(
    bili_video: video.Video,
    info: dict[str, Any],
    page: dict[str, Any],
    bvid: str,
) -> tuple[str, str]:
    cid = int(page["cid"])
    official = await fetch_official_transcript(bili_video, cid)
    if official:
        return official

    print("No official subtitles found. Falling back to local ASR.")
    return await fetch_asr_transcript(
        bili_video,
        cid,
        bvid,
        int(page.get("page") or 1),
        float(page.get("duration") or info.get("duration") or 0),
        build_access_context(info),
    )


def output_filename(bvid: str, requested_page: int | None) -> str:
    if requested_page is not None:
        return f"article_{bvid}_p{requested_page}.md"
    return f"article_{bvid}.md"


def render_markdown(
    title: str,
    bvid: str,
    page_results: list[tuple[dict[str, Any], str, str]],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"**Original Video:** https://www.bilibili.com/video/{bvid}",
        "",
        "---",
        "",
    ]

    multi_page = len(page_results) > 1
    for page, transcript, source in page_results:
        if multi_page:
            page_number = page.get("page", 1)
            part = page.get("part") or f"Page {page_number}"
            lines.extend([f"## P{page_number}: {part}", "", f"Source: {source}", ""])
        lines.extend([transcript.strip(), ""])

    return "\n".join(lines).rstrip() + "\n"


async def main(raw_input: str) -> None:
    bvid, requested_page = parse_video_input(raw_input)
    credential = await prepare_credential()
    bili_video = video.Video(bvid=bvid, credential=credential)

    try:
        info = await bili_video.get_info()
        title = info["title"]
        pages = choose_pages(info, requested_page)
        print(f"Processing: {title}")
        if requested_page is not None:
            print(f"Selected page: p={requested_page}")
        elif len(pages) > 1:
            print(f"Detected {len(pages)} pages; processing all pages.")

        page_results: list[tuple[dict[str, Any], str, str]] = []
        for page in pages:
            page_number = page.get("page", 1)
            part = page.get("part") or title
            print(f"\nProcessing page {page_number}: {part}")
            transcript, source = await fetch_page_transcript(
                bili_video,
                info,
                page,
                bvid,
            )
            page_results.append((page, transcript, source))

        filename = output_filename(bvid, requested_page)
        Path(filename).write_text(
            render_markdown(title, bvid, page_results),
            encoding="utf-8",
        )
        print(f"\nSuccess! Article saved to: {filename}")

    except TranscriptError as exc:
        print(f"Error: {exc}")
    except Exception as exc:
        print(f"An error occurred: {exc}")


if __name__ == "__main__":
    input_arg = sys.argv[1] if len(sys.argv) >= 2 else DEFAULT_BVID
    asyncio.run(main(input_arg))
