#!/usr/bin/env python3

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "site"
ASSET_SOURCE_DIR = ROOT / "assets"
ASSET_OUTPUT_DIR = OUTPUT_DIR / "assets"
CONTENT_EXCLUDES = {"README.md"}
TOP_LEVEL_SLUGS = {
    "index",
    "themen",
    "orthodoxes-glaubensbekenntnis",
    "orthodoxes-glaubensbekenntnis-verlinkt",
}
LEGAL_SLUGS = {
    "impressum",
    "datenschutz",
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
UL_RE = re.compile(r"^- (.*)$")
OL_RE = re.compile(r"^\d+\. (.*)$")
FENCE_RE = re.compile(r"^```(\w+)?\s*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
LINK_RE = re.compile(r"\[([^\]]+)\]\((<)?([^)>]+)(>)?\)")
CODE_RE = re.compile(r"`([^`]+)`")
URL_RE = re.compile(r"https?://[^\s<]+")
STRONG_RE = re.compile(r"\*\*(.+?)\*\*")
EM_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


@dataclass
class Page:
    source_path: Path
    title: str
    slug: str
    permalink: str
    body_markdown: str

    @property
    def output_path(self) -> Path:
        if self.slug == "index":
            return OUTPUT_DIR / "index.html"
        return OUTPUT_DIR / self.slug / "index.html"

    @property
    def is_root(self) -> bool:
        return self.slug == "index"

    @property
    def prefix(self) -> str:
        return "" if self.is_root else "../"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    raw_meta, body = match.groups()
    meta: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"')
    return meta, body.lstrip()


def load_pages() -> list[Page]:
    pages: list[Page] = []
    for path in sorted(ROOT.glob("*.md")):
        if path.name in CONTENT_EXCLUDES:
            continue

        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or first_heading(body) or path.stem
        slug = meta.get("slug") or path.stem
        permalink = meta.get("permalink") or ("/" if slug == "index" else f"/{slug}/")
        pages.append(
            Page(
                source_path=path,
                title=title,
                slug=slug,
                permalink=permalink,
                body_markdown=body,
            )
        )
    return pages


def first_heading(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def sort_key(page: Page) -> tuple[int, str]:
    order = {
        "index": 0,
        "themen": 1,
        "orthodoxes-glaubensbekenntnis": 2,
        "orthodoxes-glaubensbekenntnis-verlinkt": 3,
    }
    return (order.get(page.slug, 10), page.title.casefold())


def to_site_href(page: Page, href: str) -> str:
    if href.startswith(("http://", "https://", "mailto:")):
        return href
    if href == "/":
        return page.prefix or "./"
    if href.startswith("/"):
        return f"{page.prefix}{href.lstrip('/')}"
    return href


def render_inline(text: str, page: Page) -> str:
    placeholders: dict[str, str] = {}

    def stash(match: re.Match[str], replacement: str) -> str:
        token = f"@@TOKEN{len(placeholders)}@@"
        placeholders[token] = replacement
        return token

    def replace_code(match: re.Match[str]) -> str:
        code = html.escape(match.group(1))
        return stash(match, f"<code>{code}</code>")

    def replace_link(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        raw_href = match.group(3)
        href = html.escape(to_site_href(page, raw_href))
        css_class = "term-link" if not raw_href.startswith(("http://", "https://", "mailto:")) else "external-link"
        return stash(match, f'<a class="{css_class}" href="{href}">{label}</a>')

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0)
        escaped = html.escape(url)
        return stash(match, f'<a class="external-link" href="{escaped}">{escaped}</a>')

    text = CODE_RE.sub(replace_code, text)
    text = LINK_RE.sub(replace_link, text)
    text = URL_RE.sub(replace_url, text)
    text = html.escape(text)
    text = STRONG_RE.sub(r"<strong>\1</strong>", text)
    text = EM_RE.sub(r"<em>\1</em>", text)

    for token, replacement in placeholders.items():
        text = text.replace(html.escape(token), replacement)
        text = text.replace(token, replacement)

    return text


def render_paragraph(lines: list[str], page: Page) -> str:
    parts: list[str] = []
    for index, line in enumerate(lines):
        hard_break = line.endswith("  ")
        clean = line[:-2] if hard_break else line
        if index > 0 and parts and parts[-1] != "<br>":
            parts.append(" ")
        parts.append(render_inline(clean.strip(), page))
        if hard_break:
            parts.append("<br>")
    return f"<p>{''.join(parts).rstrip()}</p>"


def render_list_item(lines: list[str], page: Page) -> str:
    parts: list[str] = []
    for index, line in enumerate(lines):
        hard_break = line.endswith("  ")
        clean = line[:-2] if hard_break else line
        if index > 0 and parts and parts[-1] != "<br>":
            parts.append(" ")
        parts.append(render_inline(clean.strip(), page))
        if hard_break:
            parts.append("<br>")
    return "".join(parts).rstrip()


def render_markdown(markdown: str, page: Page) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match:
            language = fence_match.group(1) or "text"
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not FENCE_RE.match(lines[index]):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code_html = html.escape("\n".join(code_lines))
            output.append(f'<pre><code class="language-{language}">{code_html}</code></pre>')
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            text = render_inline(heading_match.group(2).strip(), page)
            output.append(f"<h{level}>{text}</h{level}>")
            index += 1
            continue

        list_match = UL_RE.match(line) or OL_RE.match(line)
        if list_match:
            ordered = bool(OL_RE.match(line))
            matcher = OL_RE if ordered else UL_RE
            items: list[str] = []

            while index < len(lines):
                item_match = matcher.match(lines[index])
                if not item_match:
                    break

                item_lines = [item_match.group(1)]
                index += 1

                while index < len(lines):
                    continuation = lines[index]
                    if not continuation.strip():
                        break
                    if HEADING_RE.match(continuation) or FENCE_RE.match(continuation):
                        break
                    if matcher.match(continuation):
                        break
                    if (OL_RE if not ordered else UL_RE).match(continuation):
                        break
                    if continuation.startswith("   ") or continuation.startswith("\t"):
                        item_lines.append(continuation.strip())
                        index += 1
                        continue
                    break

                items.append(render_list_item(item_lines, page))

                while index < len(lines) and not lines[index].strip():
                    index += 1
                    break

            tag = "ol" if ordered else "ul"
            inner = "\n".join(f"<li>{item}</li>" for item in items)
            output.append(f"<{tag}>\n{inner}\n</{tag}>")
            continue

        paragraph_lines = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                break
            if HEADING_RE.match(candidate) or FENCE_RE.match(candidate):
                break
            if UL_RE.match(candidate) or OL_RE.match(candidate):
                break
            paragraph_lines.append(candidate)
            index += 1

        output.append(render_paragraph(paragraph_lines, page))

    return "\n".join(output)


def render_sidebar(current: Page, pages: list[Page]) -> str:
    top_pages = [page for page in pages if page.slug in TOP_LEVEL_SLUGS]
    topic_pages = [
        page for page in pages if page.slug not in TOP_LEVEL_SLUGS and page.slug not in LEGAL_SLUGS
    ]
    top_pages.sort(key=sort_key)
    topic_pages.sort(key=lambda page: page.title.casefold())

    parts = ['<aside class="sidebar">', '<div class="sidebar-group">', "<h2>Navigation</h2>", "<ul>"]
    for page in top_pages:
        current_class = ' class="is-current"' if page.slug == current.slug else ""
        href = html.escape(to_site_href(current, page.permalink))
        label = html.escape(page.title)
        parts.append(f'<li><a{current_class} href="{href}">{label}</a></li>')
    parts.extend(["</ul>", "</div>", '<div class="sidebar-group">', "<h2>Themen</h2>", "<ul>"])

    for page in topic_pages:
        current_class = ' class="is-current"' if page.slug == current.slug else ""
        href = html.escape(to_site_href(current, page.permalink))
        label = html.escape(page.title)
        parts.append(f'<li><a{current_class} href="{href}">{label}</a></li>')

    parts.extend(["</ul>", "</div>", "</aside>"])
    return "\n".join(parts)


def render_page(page: Page, pages: list[Page]) -> str:
    show_sidebar = page.slug != "index" and page.slug not in LEGAL_SLUGS
    sidebar = render_sidebar(page, pages) if show_sidebar else ""
    body = render_markdown(page.body_markdown, page)
    stylesheet_href = html.escape(f"{page.prefix}assets/styles.css" if page.prefix else "assets/styles.css")
    home_href = html.escape(to_site_href(page, "/"))
    themen_href = html.escape(to_site_href(page, "/themen/"))
    credo_href = html.escape(to_site_href(page, "/orthodoxes-glaubensbekenntnis-verlinkt/"))
    impressum_href = html.escape(to_site_href(page, "/impressum/"))
    datenschutz_href = html.escape(to_site_href(page, "/datenschutz/"))
    source_label = html.escape(page.source_path.name)
    layout_class = "layout layout-home" if not show_sidebar else "layout"
    shell_class = "page-shell page-shell-home" if page.slug == "index" else "page-shell"
    article_class = "article article-home" if page.slug == "index" else "article article-subpage"
    footer_source = (
        f'<p class="page-footer-meta">Quelle: <code>{source_label}</code></p>'
        if page.slug != "index"
        else ""
    )

    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page.title)} | Credo</title>
  <link rel="stylesheet" href="{stylesheet_href}">
</head>
<body>
  <div class="{shell_class}">
    <header class="site-header">
      <a class="brand" href="{home_href}">Glaubensbekenntnis</a>
      <nav class="site-nav" aria-label="Hauptnavigation">
        <a href="{home_href}">Start</a>
        <a href="{themen_href}">Themen</a>
        <a href="{credo_href}">Verlinktes Credo</a>
      </nav>
    </header>

    <div class="{layout_class}">
      {sidebar}

      <main class="content">
        <article class="{article_class}">
          {body}
        </article>

        <footer class="page-footer">
          {footer_source}
          <nav class="legal-nav" aria-label="Rechtliches">
            <a href="{impressum_href}">Impressum</a>
            <a href="{datenschutz_href}">Datenschutz</a>
          </nav>
        </footer>
      </main>
    </div>
  </div>
</body>
</html>
"""


def build() -> None:
    pages = load_pages()
    pages.sort(key=sort_key)

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ASSET_SOURCE_DIR, ASSET_OUTPUT_DIR)

    for page in pages:
        page.output_path.parent.mkdir(parents=True, exist_ok=True)
        page.output_path.write_text(render_page(page, pages), encoding="utf-8")


if __name__ == "__main__":
    build()
