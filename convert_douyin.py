import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import yt_dlp
from dotenv import load_dotenv

from convert import TranscriptError, transcribe_with_local_asr


load_dotenv(".env")

DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3


def build_ydl_opts(
    output_template: str,
    cookies_file: str | None,
    cookies_from_browser: str | None,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)
    return opts


def resolve_cookie_source(
    cookies_arg: str | None, cookies_from_browser_arg: str | None
) -> tuple[str | None, str | None]:
    """Pick a cookie source. Precedence: explicit CLI flags, then
    DOUYIN_COOKIES_FILE, then a local douyin_cookies.txt, then live
    browser extraction (the default — see README for why a static
    cookies.txt is unreliable for Douyin specifically: it lacks
    msToken, a token the site's JS keeps rotating in a live tab)."""
    if cookies_from_browser_arg:
        return None, cookies_from_browser_arg

    if cookies_arg:
        return cookies_arg, None

    env_file = os.getenv("DOUYIN_COOKIES_FILE")
    if env_file:
        return env_file, None

    default_file = Path("douyin_cookies.txt")
    if default_file.exists():
        return str(default_file), None

    return None, os.getenv("DOUYIN_COOKIES_BROWSER", "chrome")


def download_media(url: str, ydl_opts: dict[str, Any]) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            last_exc = exc
            print(f"Download attempt {attempt}/{DOWNLOAD_ATTEMPTS} failed: {exc}")
            if attempt < DOWNLOAD_ATTEMPTS:
                print(f"Retrying in {RETRY_DELAY_SECONDS}s...")
                time.sleep(RETRY_DELAY_SECONDS)

    raise TranscriptError(
        "Could not fetch this Douyin video after "
        f"{DOWNLOAD_ATTEMPTS} attempts. Douyin's anti-bot check is "
        "intermittent even with valid cookies, so a fresh cookies.txt "
        "export or another retry sometimes helps."
    ) from last_exc


def media_path_from_info(ydl: yt_dlp.YoutubeDL, info: dict[str, Any]) -> Path:
    requested = info.get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        return Path(requested[0]["filepath"])
    return Path(ydl.prepare_filename(info))


def render_markdown(title: str, original_url: str, video_id: str, transcript: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"**Original Video:** {original_url}",
        f"**Video ID:** {video_id}",
        "",
        "---",
        "",
        "Source: local ASR (faster-whisper)",
        "",
        transcript.strip(),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(url: str, cookies_arg: str | None, cookies_from_browser_arg: str | None) -> None:
    cookies_file, cookies_from_browser = resolve_cookie_source(
        cookies_arg, cookies_from_browser_arg
    )

    if cookies_from_browser:
        print(
            f"Using live cookies from local browser profile: {cookies_from_browser}. "
            "On macOS this may prompt for Keychain access; choosing \"Always Allow\" "
            "grants standing access to that browser's entire cookie store, not just "
            "douyin.com (see README). A static --cookies file is narrower in scope "
            "but does not reliably work for this site."
        )
    else:
        print(f"Using cookies file: {cookies_file}")

    output_template = str(Path.cwd() / "douyin_%(id)s.%(ext)s")
    ydl_opts = build_ydl_opts(output_template, cookies_file, cookies_from_browser)

    print("Fetching video info and downloading media...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = download_media(url, ydl_opts)
        media_path = media_path_from_info(ydl, info)

    if not media_path.exists() or media_path.stat().st_size == 0:
        raise TranscriptError(f"Expected downloaded media at {media_path}, but it is missing.")

    video_id = str(info.get("id"))
    title = info.get("title") or video_id
    print(f"Downloaded: {media_path}")

    transcript = transcribe_with_local_asr(media_path)

    filename = f"article_douyin_{video_id}.md"
    Path(filename).write_text(
        render_markdown(title, url, video_id, transcript),
        encoding="utf-8",
    )
    print(f"\nSuccess! Article saved to: {filename}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a Douyin video into a Markdown article via local ASR."
    )
    parser.add_argument("url", help="Douyin video URL or short link (v.douyin.com/...)")
    parser.add_argument(
        "--cookies",
        help=(
            "Path to a Netscape-format cookies.txt for douyin.com (see README). "
            "Narrower in scope than --cookies-from-browser, but Douyin rotates a "
            "token (msToken) that a static file can't capture, so this often fails."
        ),
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help=(
            "Read cookies live from a local browser profile (default: 'chrome' "
            "if no other cookie source is found). Grants that browser's entire "
            "cookie store, decrypted via macOS Keychain access — but is the only "
            "method that reliably works against Douyin's rotating anti-bot token."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    try:
        main(args.url, args.cookies, args.cookies_from_browser)
    except TranscriptError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
