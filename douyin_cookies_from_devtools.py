import datetime
import sys
import time
from pathlib import Path

HEADER_KEYWORDS = {"name", "value", "domain", "path", "expires", "max-age"}


def looks_like_header(line: str) -> bool:
    tokens = {t.strip().lower() for t in line.split("\t")}
    return bool(tokens & HEADER_KEYWORDS)


def find_column(headers: list[str], *candidates: str) -> int | None:
    lowered = [h.strip().lower() for h in headers]
    for candidate in candidates:
        if candidate in lowered:
            return lowered.index(candidate)
    return None


def parse_expiry(raw: str, fallback: float) -> int:
    raw = raw.strip()
    if not raw or raw.lower() in {"session", "-"}:
        return int(fallback)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.datetime.strptime(raw, fmt).replace(tzinfo=datetime.timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    try:
        return int(float(raw))
    except ValueError:
        return int(fallback)


def to_netscape_line(domain: str, path: str, name: str, value: str, expiry: int) -> str:
    include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
    return "\t".join(
        [domain, include_subdomains, path or "/", "TRUE", str(expiry), name, value]
    )


def main() -> None:
    print(
        "Paste the copied cookie table from DevTools "
        "(Application > Cookies > https://www.douyin.com — select the rows, "
        "copy, paste here), then press Ctrl-D when done:",
        file=sys.stderr,
    )
    raw = sys.stdin.read()
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        print("No input received.", file=sys.stderr)
        sys.exit(1)

    fallback_expiry = time.time() + 365 * 24 * 3600

    name_idx, value_idx = 0, 1
    domain_idx: int | None = 2
    path_idx: int | None = 3
    expiry_idx: int | None = 4
    start = 0

    if looks_like_header(lines[0]):
        headers = lines[0].split("\t")
        name_idx = find_column(headers, "name") or 0
        value_idx = find_column(headers, "value") or 1
        domain_idx = find_column(headers, "domain")
        path_idx = find_column(headers, "path")
        expiry_idx = find_column(headers, "expires / max-age", "expires", "max-age")
        start = 1

    out_lines = ["# Netscape HTTP Cookie File"]
    count = 0
    for line in lines[start:]:
        cols = line.split("\t")
        if len(cols) <= max(name_idx, value_idx):
            continue
        name = cols[name_idx].strip()
        value = cols[value_idx].strip()
        if not name or not value:
            continue

        domain = ""
        if domain_idx is not None and domain_idx < len(cols):
            domain = cols[domain_idx].strip()
        domain = domain or ".douyin.com"

        path = "/"
        if path_idx is not None and path_idx < len(cols):
            path = cols[path_idx].strip() or "/"

        expiry_raw = ""
        if expiry_idx is not None and expiry_idx < len(cols):
            expiry_raw = cols[expiry_idx].strip()
        expiry = parse_expiry(expiry_raw, fallback_expiry)

        out_lines.append(to_netscape_line(domain, path, name, value, expiry))
        count += 1

    if count == 0:
        print("Could not parse any cookies from the input.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("douyin_cookies.txt")
    output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"Wrote {count} cookies to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
