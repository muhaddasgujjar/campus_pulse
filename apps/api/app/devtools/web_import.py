"""One-time import of public pages from the institution's website (user decision, 2026-10-05).

This is not a scraping pipeline (D1 stands): it runs by hand, once or when staff ask for a
refresh. It writes a JSON snapshot to seed/<slug>/web/ for review; `app.cli doc import-web`
then loads the pages as *pending* documents. Nothing is used for answers until a staff member
approves it (D6), which is also when it is chunked and embedded.

Politeness: robots.txt is honoured, hosts must be on the institution's allowlist, one request
per second by default, and only pages a student would ask about are selected.

Usage (from apps/api):  uv run python -m app.devtools.web_import ../../seed/lgu [--limit N]
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "CampusPulse-FYP-import/1.0 (student final year project; one-time import)"

# Pages a student would ask about. Matched against the URL path.
INCLUDE = re.compile(
    r"admission|apply|eligib|criteria|fee|scholarship|polic|regulation|handbook|exams?/|"
    r"accounts/|registrar-(home|forms)|contact|offices/|students-affair|career-development|"
    r"counselling|e-library|facilities|programs-offered|courses/|merit-list|/result/|/noc/|"
    r"how-can-we-help|road-?map|overview|award-of|structure-of|test-guidelines|"
    r"post-associate|associate-and-post|programs/$|-programs/$|^/(bs|ms|mba|bba|adp|phd)|"
    r"bachelor|master|doctor-of|associate-degree",
    re.IGNORECASE,
)
EXCLUDE = re.compile(
    r"login|register|account|password|logout|/users?/|members|profile|forgot|reset|/change/|"
    r"/test/|maintenance|thank-you|icms|itics|/icc-|conference|call-for-paper|event|news|"
    r"gallery|team|organogram|message|vision|core-values|publication|journal|panelist|keynote|"
    r"speaker|chief-guest|amlctf|imc-20|icssr|ai2cf|icop|banner|tentative|session-chairs|"
    r"donor|donation|tender|newsletter|qec|webinar|testimonial|virtual-campus|success-stories|"
    r"cloned|chat-with|request-more|join-a|data-protection|lab-attendants|achievement",
    re.IGNORECASE,
)

CATEGORIES = (
    ("fees", re.compile(r"fee", re.I)),
    ("admissions", re.compile(r"admission|apply|eligib|criteria|merit|test-guidelines", re.I)),
    ("scholarships", re.compile(r"scholarship", re.I)),
    ("policies", re.compile(r"polic|regulation|handbook|noc", re.I)),
    ("exams", re.compile(r"exam|result", re.I)),
    ("contacts", re.compile(r"contact|offices|accounts|registrar|affair|counselling|career", re.I)),
    ("programs", re.compile(r".", re.I)),
)

# WordPress puts a hidden "<title><author><modified ISO time>" line at the top of the content.
_MODIFIED = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")

_SKIP = {"script", "style", "noscript", "svg", "nav", "form", "iframe", "button", "select"}
_BLOCK = {
    "p", "div", "section", "article", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "h5",
    "h6", "tr", "table", "thead", "tbody", "blockquote", "header", "footer",
}  # fmt: skip


class MainText(HTMLParser):
    """Text of <main> (WordPress/Avada content area), tables as `cell | cell` rows."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._main_depth = 0
        self._skip_depth = 0
        self._parts: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag == "main":
            self._main_depth += 1
        if not self._main_depth:
            return
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag in _BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if not self._main_depth:
            return
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            cells = [c for c in self._row if c]
            if cells:
                self._parts.append("\n" + " | ".join(cells) + "\n")
            self._row = None
        elif tag in _BLOCK:
            self._parts.append("\n")
        if tag == "main":
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if not self._main_depth or self._skip_depth:
            return
        if self._cell is not None:
            self._cell.append(data)
        else:
            self._parts.append(data)

    def text(self) -> tuple[str, str | None]:
        """(content, page modified date or None)."""
        lines = (" ".join(line.split()) for line in "".join(self._parts).splitlines())
        out: list[str] = []
        modified: str | None = None
        for line in lines:
            stamp = _MODIFIED.search(line)
            if stamp and len(line) < 200:
                modified = modified or stamp.group(1)
                continue
            if line and (not out or out[-1] != line):  # drop blanks and repeated lines
                out.append(line)
        return "\n".join(out), modified


@dataclass
class Page:
    url: str
    title: str
    category: str
    content: str
    page_modified: str | None
    fetched_at: str
    sha256: str


def select_urls(urls: list[str], allowed_hosts: list[str]) -> list[str]:
    chosen = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.hostname not in allowed_hosts:
            continue
        path = parsed.path or "/"
        if INCLUDE.search(path) and not EXCLUDE.search(path):
            chosen.append(url)
    return sorted(set(chosen))


def category_for(path: str) -> str:
    return next(name for name, pattern in CATEGORIES if pattern.search(path))


def clean_title(raw: str, short_name: str) -> str:
    title = " ".join(raw.split())
    for sep in (" - ", " | ", f" {chr(0x2013)} "):  # hyphen, bar, en dash
        if sep in title:
            title = title.split(sep)[0]
    return title.strip() or short_name


def extract(html: str) -> tuple[str, str, str | None]:
    """(page title, main content, page modified date)."""
    parser = MainText()
    parser.feed(html)
    content, modified = parser.text()
    return parser.title, content, modified


async def _sitemap_urls(client: httpx.AsyncClient, root: str) -> list[str]:
    loc = re.compile(r"<loc>([^<]+)</loc>")
    index = (await client.get(f"{root}/wp-sitemap.xml")).text
    urls: list[str] = []
    for sitemap in loc.findall(index):
        if "posts-page" in sitemap:  # pages only: posts are news, users are people
            urls += loc.findall((await client.get(sitemap)).text)
    return urls


async def run(seed_dir: Path, *, delay: float, limit: int | None, min_chars: int) -> Path:
    meta = json.loads((seed_dir / "institution.json").read_text(encoding="utf-8"))
    hosts: list[str] = meta["config"]["live_fetch_allowlist"]
    short_name = meta["config"].get("short_name", meta["slug"])
    root = f"https://{hosts[0]}"
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        robots = RobotFileParser()
        robots.parse((await client.get(f"{root}/robots.txt")).text.splitlines())
        urls = select_urls(await _sitemap_urls(client, root), hosts)
        urls = [u for u in urls if robots.can_fetch(USER_AGENT, u)][:limit]
        print(f"{len(urls)} pages selected", file=sys.stderr)
        pages: list[Page] = []
        for number, url in enumerate(urls, start=1):
            await asyncio.sleep(delay)
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                print(f"[{number}/{len(urls)}] skip {url}: {type(exc).__name__}", file=sys.stderr)
                continue
            if response.status_code != 200 or "html" not in response.headers.get(
                "content-type", ""
            ):
                print(f"[{number}/{len(urls)}] skip {url}: {response.status_code}", file=sys.stderr)
                continue
            raw_title, content, modified = extract(response.text)
            if len(content) < min_chars:
                print(f"[{number}/{len(urls)}] skip {url}: too little text", file=sys.stderr)
                continue
            pages.append(
                Page(
                    url=url,
                    title=clean_title(raw_title, short_name),
                    category=category_for(urlparse(url).path),
                    content=content,
                    page_modified=modified,
                    fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
                    sha256=hashlib.sha256(content.encode()).hexdigest(),
                )
            )
            print(f"[{number}/{len(urls)}] ok {url} ({len(content)} chars)", file=sys.stderr)
    out = seed_dir / "web" / f"{meta['slug']}_website_{datetime.now(UTC):%Y-%m-%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": root,
        "note": "One-time import of public pages. Loaded as PENDING documents: staff must "
        "check each page with the office and approve it before it is used (D6).",
        "pages": [asdict(p) for p in pages],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One-time import of public website pages.")
    parser.add_argument("seed_dir", type=Path)
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-chars", type=int, default=200)
    args = parser.parse_args(argv)
    out = asyncio.run(
        run(args.seed_dir, delay=args.delay, limit=args.limit, min_chars=args.min_chars)
    )
    print(f"Snapshot: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
