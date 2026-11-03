#!/usr/bin/env python3
"""Build the blog into a folder of plain files (default: public/). Standard library only.

    python build.py                  # build, drafts included (draft posts get a badge, draft-only notes are visible)
    python build.py --publish        # the version to upload: no drafts, no draft-only notes, nothing hidden by CSS
    python build.py --check          # build, then verify every link, image, script and font in the output exists
    python build.py --out site       # another output folder (it is cleared first, but only if this tool made it)
    python build.py --site ../my-blog   # build another folder's site with this engine (see "One engine, several sites" in the README)

Sources: site.json, content/posts/*.html, content/pages/*.html (pages are not listed on the home page), content/drafts/*.html
(posts that are always drafts: a place for work in progress that you keep out of git), content/images/*,
theme/. Each content file starts with a front-matter block and continues with the HTML of the page body:

    ---
    title: Three ways to imagine a forest trail
    date: 2026-10-26
    description: One sentence for the home page, search results and link previews.
    links: Code | https://github.com/you/repo; Paper | https://arxiv.org/abs/0000.00000
    image: images/teaser.jpg
    toc: true
    draft: true
    ---
    <p>Body HTML ... see the components post for everything you can put here.</p>
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import os
import unicodedata
from urllib.parse import unquote
import shlex
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

ENGINE = Path(__file__).resolve().parent                # the code, the theme and the built-in components
ROOT = ENGINE                                           # the site built by default: this folder (the template's own example site)
MARKER = ".blog-template-build"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
RESERVED = {"theme", "images", "feed", "sitemap", "index"}
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
SECTION_RESERVED = RESERVED | {"content"}                 # section addresses are also ids on the home page; "content" is <main>


class BuildError(Exception):
    """Something the author must fix; reported as a plain message, not a traceback."""


# ---- reading content ------------------------------------------------------------------------------------------------
def parse_front_matter(text, source):
    text = text.replace("\r\n", "\n").lstrip("﻿")
    m = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", text, re.S)
    if not m:
        raise BuildError(f"{source}: the file must start with a front-matter block between two '---' lines")
    meta = {}
    for n, line in enumerate(m.group(1).split("\n"), 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep or not key.strip():
            raise BuildError(f"{source}:{n}: expected 'key: value', got {line!r}")
        meta[key.strip().lower()] = value.strip()
    return meta, m.group(2)


def safe_url(url, where):
    if re.match(r"(javascript|data|vbscript):", re.sub(r"[\x00-\x20]+", "", url), re.I):
        raise BuildError(f"{where}: refusing the link {url[:40]!r} (only web, mailto, relative and # links are allowed)")
    return url


def parse_links(value, where):
    links = []
    for part in filter(None, (p.strip() for p in value.split(";"))):
        label, sep, url = part.partition("|")
        if not sep or not label.strip():
            raise BuildError(f"{where}: links must look like 'Label | https://...; Label | https://...'")
        if url.strip() in ("", "#"):
            continue                                     # not filled in yet ("Code |" or "Code | #"): the button stays hidden
        links.append((label.strip(), safe_url(url.strip(), where)))
    return links


def truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def local_files(value, path, key):
    """A comma-separated list of files that live next to the page (in its folder); nothing absolute, remote or above it."""
    refs = []
    for part in (x.strip() for x in value.split(",")):
        if not part:
            continue
        bare = part.split("?")[0].split("#")[0]
        if not bare or re.match(r"([a-z][a-z0-9+.-]*:|/|\\)", part, re.I) or ".." in bare.replace("\\", "/").split("/"):
            raise BuildError(f"{path}: '{key}' may only list files in the page's own folder (like figures.js), got {part!r}")
        refs.append(part)
    return refs


def load_entry(path, kind):
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
    slug = meta.get("slug") or path.stem
    if not SLUG.match(slug) or slug in RESERVED:
        raise BuildError(f"{path}: '{slug}' is not a usable address; use lower-case letters, digits and '-' (reserved: {sorted(RESERVED)})")
    if not meta.get("title"):
        raise BuildError(f"{path}: a title is required")
    date = None
    if kind == "post" or meta.get("date"):
        try:
            date = dt.date.fromisoformat(meta.get("date", ""))
        except ValueError:
            raise BuildError(f"{path}: date must be written YYYY-MM-DD, got {meta.get('date')!r}") from None
    return {"kind": kind, "slug": slug, "title": meta["title"], "date": date, "description": meta.get("description", ""),
            "draft": truthy(meta.get("draft", "")),
            "section": meta.get("section", "").strip(), "image": meta.get("image", ""), "authors": meta.get("authors", ""), "toc": truthy(meta.get("toc", "")),
            "links": parse_links(meta.get("links", ""), path), "body": body, "source": path,
            "styles": local_files(meta.get("styles", ""), path, "styles"), "scripts": local_files(meta.get("scripts", ""), path, "scripts")}


def load_site(root=ROOT):
    try:
        site = json.loads((root / "site.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BuildError(f"{root / 'site.json'} not found") from None
    except ValueError as e:
        raise BuildError(f"site.json is not valid JSON ({e})") from None
    if not isinstance(site, dict):
        raise BuildError("site.json must contain a JSON object")
    for key in ("title", "author"):
        if not site.get(key):
            raise BuildError(f"site.json: '{key}' is required")
    for key in ("title", "author", "lang", "description", "intro", "url", "posts_heading", "posts_slug"):
        if key in site and not isinstance(site[key], str):
            raise BuildError(f"site.json: '{key}' must be text")
    for key in ("nav", "sections"):
        if key in site and not isinstance(site[key], list):
            raise BuildError(f"site.json: '{key}' must be a list")
    if "footer" in site and not (isinstance(site["footer"], str) or site["footer"] is False):
        raise BuildError("site.json: 'footer' must be text (HTML), or false for no footer")
    for i, item in enumerate(site.get("nav", [])):
        if not (isinstance(item, dict) and isinstance(item.get("label"), str) and isinstance(item.get("href"), str)):
            raise BuildError(f"site.json: nav item {i + 1} must look like {{\"label\": \"About\", \"href\": \"about/index.html\"}}")
    for i, sec in enumerate(site.get("sections", [])):
        if not (isinstance(sec, dict) and isinstance(sec.get("id"), str) and SLUG.match(sec["id"]) and sec["id"] != "posts"
                and isinstance(sec.get("heading"), str)):
            raise BuildError(f"site.json: section {i + 1} must look like {{\"id\": \"crosswords\", \"heading\": \"Crosswords\"}} "
                             "(a lower-case id other than 'posts')")
    for sec in site.get("sections", []):
        if "reading_time" in sec and not isinstance(sec["reading_time"], bool):
            raise BuildError(f"site.json: section '{sec['id']}': 'reading_time' must be true or false")
    slugs = [site.get("posts_slug", "posts")] + [s["id"] for s in site.get("sections", [])]
    if len(set(slugs)) != len(slugs):
        raise BuildError("site.json: section ids, and posts_slug, must be unique")
    for slug in slugs:
        if not SLUG.match(slug) or slug in SECTION_RESERVED:
            raise BuildError(f"site.json: '{slug}' is not a usable section address; use lower-case letters, digits and '-' (reserved: {sorted(SECTION_RESERVED)})")
    if site.get("url") and not re.match(r"https?://[^/\s]+", site["url"]):
        raise BuildError("site.json: 'url' must start with https:// (or http://), for example https://you.example")
    site.setdefault("lang", "en")
    site.setdefault("description", "")
    site.setdefault("intro", "")
    site.setdefault("footer", "")
    site.setdefault("posts_heading", "Posts")
    site.setdefault("sections", [])
    site.setdefault("posts_slug", "posts")
    site.setdefault("dark_mode", False)
    site.setdefault("author_pages", False)
    for key in ("dark_mode", "author_pages"):
        if not isinstance(site[key], bool):
            raise BuildError(f"site.json: '{key}' must be true or false")
    site.setdefault("nav", [])
    site["url"] = site.get("url", "").rstrip("/")
    return site


def load_entries(root=ROOT):
    entries, seen = [], {}
    for kind, folder in (("post", "posts"), ("page", "pages"), ("post", "drafts")):
        for path in sorted((root / "content" / folder).glob("*.html")):
            e = load_entry(path, kind)
            if folder == "drafts":
                e["draft"] = True                       # content/drafts/ is for work in progress: built locally, never published
            if e["slug"] in seen:
                raise BuildError(f"{path}: the address '{e['slug']}' is already used by {seen[e['slug']]}")
            seen[e["slug"]] = path
            entries.append(e)
    return entries


# ---- transforming the body ------------------------------------------------------------------------------------------
class DraftStripper(HTMLParser):
    """Copies HTML unchanged except that every element with class 'draft-only' (and what is inside it) is left out."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.skip_tag, self.depth = [], None, 0

    def handle_starttag(self, tag, attrs):
        if self.skip_tag:
            if tag == self.skip_tag and tag not in VOID:
                self.depth += 1
            return
        if "draft-only" in (dict(attrs).get("class") or "").split() and tag not in VOID:
            self.skip_tag, self.depth = tag, 1
            return
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if not self.skip_tag:
            self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.skip_tag:
            if tag == self.skip_tag:
                self.depth -= 1
                if self.depth == 0:
                    self.skip_tag = None
            return
        self.out.append(f"</{tag}>")

    def _keep(self, text):
        if not self.skip_tag:
            self.out.append(text)

    def handle_data(self, data):
        self._keep(data)

    def handle_entityref(self, name):
        self._keep(f"&{name};")

    def handle_charref(self, name):
        self._keep(f"&#{name};")

    def handle_comment(self, data):
        self._keep(f"<!--{data}-->")

    def handle_decl(self, decl):
        self._keep(f"<!{decl}>")

    def handle_pi(self, data):
        self._keep(f"<?{data}>")

    def unknown_decl(self, data):
        self._keep(f"<![{data}]]>" if data.startswith("CDATA[") else f"<![{data}]>")


def strip_draft_only(body):
    p = DraftStripper()
    p.feed(body)
    p.close()
    return "".join(p.out)


# ---- reusable components: shortcodes and snippets -------------------------------------------------------------------------
# A snippet is an HTML file with placeholders. It lives in content/snippets/NAME.html (yours, wins) or theme/components/NAME.html
# (built in). A post calls it with   {{name arg "two words" key=value}}   or around some HTML with   {{#name key=value}}...{{/name}}.
# In the snippet: {{key}} is the value HTML-escaped, {{{key}}} the value as it is, {{key|default}} a default, {{1}} the first plain
# argument, {{{body}}} the HTML between {{#name}} and {{/name}}, {{{root}}} the path back to the site root ("" or "../").
# Snippets cannot call other snippets; the HTML between a block's tags can. Text inside <pre>, <code>, <script> and <style> is
# never touched, and \{{ writes a literal {{.
SHORTCODE = re.compile(r"\{\{\s*([#/]?)\s*([A-Za-z][\w-]*)\s*(.*?)\}\}", re.S)
PLACEHOLDER = re.compile(r"\{\{\{\s*(\w+)\s*(?:\|([^{}]*))?\}\}\}|\{\{\s*(\w+)\s*(?:\|([^{}]*))?\}\}")
PROTECTED = re.compile(r"<(pre|code|script|style)\b[^>]*>.*?</\1\s*>", re.S | re.I)
ESCAPED_BRACES = chr(0) + "LB" + chr(0)                   # stands in for an escaped brace pair while expanding
SNIPPET_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")
RESERVED_PARAMS = {"body", "root"}


class Ctx:
    """What a shortcode needs to know about the page it is on."""

    def __init__(self, root_dir, page_root, where, engine=None):
        self.root_dir, self.page_root, self.where = Path(root_dir), page_root, where
        self.engine = Path(engine) if engine else ENGINE
        self.kept, self.mark = [], chr(0) + "KEEP"

    def restore(self, text):
        return re.sub(re.escape(self.mark) + r"(\d+)" + re.escape(chr(0)), lambda m: self.kept[int(m.group(1))], text)


def snippet_folders(ctx):
    """Where pieces are looked up, first match wins: the site's own, the site's theme overrides, the engine's built-ins."""
    return (ctx.root_dir / "content" / "snippets", ctx.root_dir / "theme" / "components", ctx.engine / "theme" / "components")


def find_snippet(name, ctx):
    for folder in snippet_folders(ctx):
        path = folder / f"{name}.html"
        if SNIPPET_NAME.match(name) and path.exists():
            return path
    names = sorted({p.stem for folder in snippet_folders(ctx) for p in folder.glob("*.html")} | {"svg", "crossword"})
    raise BuildError(f"{ctx.where}: there is no snippet called '{name}' (available: {', '.join(names)}). "
                     f"To write a literal {{{{ in the text, put a backslash before it.")


def parse_args(argstr, name, ctx):
    try:
        tokens = shlex.split(ctx.restore(argstr).replace(ESCAPED_BRACES, "{{"))
    except ValueError as e:
        raise BuildError(f"{ctx.where}: cannot read the arguments of '{name}' ({e}); quote values that contain spaces or apostrophes "
                         f"with double quotes") from None
    named, positional = {}, []
    for t in tokens:
        m = re.match(r"([A-Za-z]\w*)=(.*)\Z", t, re.S)
        if m:
            named[m.group(1)] = m.group(2)
        else:
            positional.append(t)
    return positional, named


def inline_svg(positional, named, ctx):
    src = named.get("src") or (positional[0] if positional else "")
    images = (ctx.root_dir / "content" / "images").resolve()
    path = (images / src).resolve()
    if not src or images not in path.parents or path.suffix.lower() != ".svg" or not path.is_file():
        raise BuildError(f"{ctx.where}: {{{{svg}}}} needs the name of an .svg file inside content/images/, got {src!r}")
    text, prolog = path.read_text(encoding="utf-8").strip(), re.compile(r"(<\?xml.*?\?>|<!DOCTYPE[^>]*>|<!--.*?-->)\s*", re.S | re.I)
    while prolog.match(text):
        text = text[prolog.match(text).end():]
    if not text.startswith("<svg"):
        raise BuildError(f"{ctx.where}: {path.name} does not start with <svg")
    return text


MAX_GRID = 40


def crossword_error(where, message):
    return BuildError(f"{where}: crossword: {message}")


def ipuz_cell_value(cell):
    """The letter in a solution cell (a plain string, or {"value": "A"}), or None for no value."""
    if isinstance(cell, dict):
        cell = cell.get("value")
    return cell if isinstance(cell, str) else None


def number_grid(solution):
    """Standard crossword numbering of a grid of letters ('#' is a block): ({(row, col): number}, across words, down words);
    a word is (number, [(row, col), ...])."""
    h, w = len(solution), len(solution[0])
    numbers, across, down, n = {}, [], [], 0
    for r in range(h):
        for c in range(w):
            if solution[r][c] == "#":
                continue
            starts_across = (c == 0 or solution[r][c - 1] == "#") and c + 1 < w and solution[r][c + 1] != "#"
            starts_down = (r == 0 or solution[r - 1][c] == "#") and r + 1 < h and solution[r + 1][c] != "#"
            if starts_across or starts_down:
                n += 1
                numbers[(r, c)] = n
            if starts_across:
                end = c
                while end < w and solution[r][end] != "#":
                    end += 1
                across.append((n, [(r, k) for k in range(c, end)]))
            if starts_down:
                end = r
                while end < h and solution[end][c] != "#":
                    end += 1
                down.append((n, [(k, c) for k in range(r, end)]))
    return numbers, across, down


def read_ipuz(path, where):
    """Read an .ipuz crossword (https://ipuz.org) into the compact form the player uses; anything unsupported is a BuildError.
    Supported: rectangular grids with blocks, one letter or digit per square, Across/Down clues, circled squares (style.shapebg)."""
    text = path.read_text(encoding="utf-8-sig").strip()
    m = re.match(r"ipuz\((.*)\);?\Z", text, re.S)                     # some tools wrap the JSON the old JSONP way
    try:
        raw = json.loads(m.group(1) if m else text)
    except ValueError as e:
        raise crossword_error(where, f"{path.name} is not valid JSON ({e})") from None
    if not isinstance(raw, dict):
        raise crossword_error(where, f"{path.name} must contain a JSON object")
    kinds = raw.get("kind")
    if not (isinstance(kinds, list) and any(isinstance(k, str) and "ipuz.org/crossword" in k for k in kinds)):
        raise crossword_error(where, f"{path.name} is not an ipuz crossword (its \"kind\" must name http://ipuz.org/crossword#1)")
    dims = raw.get("dimensions")
    try:
        w, h = int(dims["width"]), int(dims["height"])
    except (TypeError, KeyError, ValueError):
        raise crossword_error(where, f"{path.name}: \"dimensions\" must give a width and a height") from None
    if not (2 <= w <= MAX_GRID and 2 <= h <= MAX_GRID):
        raise crossword_error(where, f"{path.name}: the grid must be between 2 and {MAX_GRID} squares each way, got {w} by {h}")
    block = raw.get("block", "#")
    rows, puzzle = raw.get("solution"), raw.get("puzzle")
    for name, grid in (("solution", rows), ("puzzle", puzzle)):
        if not (isinstance(grid, list) and len(grid) == h and all(isinstance(row, list) and len(row) == w for row in grid)):
            raise crossword_error(where, f"{path.name}: \"{name}\" must be {h} rows of {w} squares to match \"dimensions\"")
    solution, circles = [], []
    for r in range(h):
        line = []
        for c in range(w):
            cell, pcell = rows[r][c], puzzle[r][c]
            value = ipuz_cell_value(cell)
            pvalue = pcell.get("cell") if isinstance(pcell, dict) else pcell
            if cell is None or pcell is None or pvalue == block or value in (block, "#"):
                line.append("#")
                continue
            if not value:
                raise crossword_error(where, f"{path.name}: the square in row {r + 1}, column {c + 1} has no solution letter")
            if len(value) != 1 or not value.isalnum():
                raise crossword_error(where, f"{path.name}: the square in row {r + 1}, column {c + 1} holds {value!r}; "
                                              "only one letter or digit per square is supported (no rebus squares)")
            line.append(value.upper())
            style = pcell.get("style") if isinstance(pcell, dict) else None
            if isinstance(style, dict) and style.get("shapebg") == "circle":
                circles.append([r, c])
        solution.append("".join(line))
    numbers, across, down = number_grid(solution)
    clues = raw.get("clues")
    if not isinstance(clues, dict):
        raise crossword_error(where, f"{path.name}: \"clues\" must have \"Across\" and \"Down\" lists")
    found = {}
    for direction, words in (("Across", across), ("Down", down)):
        entries = clues.get(direction)
        if not isinstance(entries, list):
            raise crossword_error(where, f"{path.name}: \"clues\" has no \"{direction}\" list")
        table = {}
        for entry in entries:
            if isinstance(entry, dict):
                number, clue = entry.get("number"), entry.get("clue")
            elif isinstance(entry, list) and len(entry) >= 2:
                number, clue = entry[0], entry[1]
            else:
                raise crossword_error(where, f"{path.name}: a {direction} clue must look like [number, \"text\"]")
            if not isinstance(clue, str) or not clue.strip():
                raise crossword_error(where, f"{path.name}: {direction} clue {number} has no text")
            try:
                number = int(number)
            except (TypeError, ValueError):
                raise crossword_error(where, f"{path.name}: {direction} clue number {number!r} is not a number") from None
            if number in table:
                raise crossword_error(where, f"{path.name}: {direction} clue {number} appears twice")
            table[number] = clue.strip()
        have, want = set(table), {n for n, _ in words}
        if have != want:
            problems = [f"missing {sorted(want - have)}" if want - have else "", f"no such word {sorted(have - want)}" if have - want else ""]
            raise crossword_error(where, f"{path.name}: the {direction} clues do not match the grid ({', '.join(p for p in problems if p)}); "
                                         "numbers are counted from the solution grid")
        found[direction] = [[n, table[n]] for n, _ in words]
    meta = {key: raw[key].strip() for key in ("title", "author", "notes") if isinstance(raw.get(key), str) and raw[key].strip()}
    ident = hashlib.sha1((f"{w}x{h}:" + "/".join(solution)).encode("utf-8")).hexdigest()[:12]
    return {"id": ident, "w": w, "h": h, "grid": solution, "across": found["Across"], "down": found["Down"], "circles": circles, **meta}


def crossword_html(puzzle, root):
    """The markup for one crossword: a data block the player reads, a no-JavaScript fallback with the clues, and the player script."""
    blob = (json.dumps(puzzle, separators=(",", ":"), ensure_ascii=True)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))              # nothing in the data can close the script block
    title = f"<b>{esc(puzzle['title'])}</b>" if puzzle.get("title") else ""
    by = f" by {esc(puzzle['author'])}" if puzzle.get("author") else ""
    meta = f'<p class="cw-meta">{title}{by}</p>' if title or by else ""

    def listing(label, key):
        return f"<p><b>{label}</b></p><ol>" + "".join(f'<li value="{n}">{esc(c)}</li>' for n, c in puzzle[key]) + "</ol>"
    return (f'<div class="crossword wide" data-id="{puzzle["id"]}">{meta}<script type="application/json" class="crossword-data">{blob}</script>'
            f'<noscript><p>This crossword needs JavaScript to play. The clues:</p>{listing("Across", "across")}{listing("Down", "down")}</noscript></div>'
            f'<script src="{root}theme/crossword.js" defer></script>')


def render_crossword(positional, named, ctx):
    src = named.get("src") or (positional[0] if positional else "")
    if not isinstance(ctx.where, Path):
        raise BuildError(f"{ctx.where}: {{{{crossword}}}} works in posts and pages, not here")
    folder = ctx.where.with_suffix("").resolve()
    path = (folder / src).resolve()
    if not src or folder not in path.parents or path.suffix.lower() not in (".ipuz", ".json") or not path.is_file():
        raise BuildError(f"{ctx.where}: {{{{crossword}}}} needs the name of an .ipuz file in the post's own folder "
                         f"({folder.name}/), got {src!r}")
    return crossword_html(read_ipuz(path, ctx.where), ctx.page_root)


def render_snippet(name, positional, named, body, is_block, ctx):
    if name == "svg":
        return inline_svg(positional, named, ctx)
    if name == "crossword":
        if is_block:
            raise BuildError(f"{ctx.where}: 'crossword' does not wrap content; write {{{{crossword file.ipuz}}}}")
        return render_crossword(positional, named, ctx)
    path = find_snippet(name, ctx)
    template = path.read_text(encoding="utf-8")
    declared = {}
    for m in PLACEHOLDER.finditer(template):
        declared.setdefault(m.group(1) or m.group(3), None)
    params = {k for k in declared if k not in RESERVED_PARAMS and not k.isdigit()}
    slots = {int(k) for k in declared if k.isdigit()}
    unknown = sorted(set(named) - params)
    if unknown:
        raise BuildError(f"{ctx.where}: '{name}' has no parameter {unknown[0]!r}; it takes: "
                         f"{', '.join(sorted(params) + [str(i) for i in sorted(slots)] + (['a body'] if 'body' in declared else [])) or 'nothing'}")
    if len(positional) > max(slots, default=0):
        raise BuildError(f"{ctx.where}: '{name}' takes {max(slots, default=0)} plain argument(s), got {len(positional)}")
    if is_block and "body" not in declared:
        raise BuildError(f"{ctx.where}: '{name}' does not wrap content; write {{{{{name} ...}}}} without #, and no {{{{/{name}}}}}")
    values = {**named, **{str(i + 1): v for i, v in enumerate(positional)}}

    def fill(m):
        key, raw = (m.group(1), True) if m.group(1) else (m.group(3), False)
        default = m.group(2) if m.group(1) else m.group(4)
        if key == "body":
            return body
        if key == "root":
            return ctx.page_root
        if key in values:
            return values[key] if raw else html.escape(values[key], quote=True)
        if default is not None:
            return default
        raise BuildError(f"{ctx.where}: '{name}' needs {'argument ' + key if key.isdigit() else repr(key)}")
    return PLACEHOLDER.sub(fill, template).strip()


def expand_text(text, ctx):
    """Expand shortcodes in a piece of HTML that contains no protected elements."""
    out, stack, pos = [[]], [], 0
    for m in SHORTCODE.finditer(text):
        out[-1].append(text[pos:m.start()])
        pos = m.end()
        kind, name, argstr = m.group(1), m.group(2), m.group(3)
        if kind == "/":
            if not stack or stack[-1][0] != name:
                raise BuildError(f"{ctx.where}: {{{{/{name}}}}} closes nothing" if not stack else
                                 f"{ctx.where}: {{{{/{name}}}}} where {{{{/{stack[-1][0]}}}}} was expected")
            opened, args = stack.pop()
            body = "".join(out.pop())
            positional, named = parse_args(args, opened, ctx)
            out[-1].append(render_snippet(opened, positional, named, body, True, ctx))
        elif kind == "#":
            stack.append((name, argstr))
            out.append([])
        else:
            positional, named = parse_args(argstr, name, ctx)
            out[-1].append(render_snippet(name, positional, named, "", False, ctx))
    out[-1].append(text[pos:])
    if stack:
        raise BuildError(f"{ctx.where}: {{{{#{stack[-1][0]}}}}} is never closed with {{{{/{stack[-1][0]}}}}}")
    return "".join(out[0])


def expand_shortcodes(text, ctx):
    """Expand every shortcode in `text`. Code and scripts are set aside first (so a shortcode may wrap them, and their own
    text is never touched) and put back afterwards."""
    def keep(m):
        ctx.kept.append(m.group(0))
        return f"{ctx.mark}{len(ctx.kept) - 1}{chr(0)}"
    text = PROTECTED.sub(keep, text).replace("\\{{", ESCAPED_BRACES)
    return ctx.restore(expand_text(text, ctx).replace(ESCAPED_BRACES, "{{"))


def slugify(text):
    text = re.sub(r"<[^>]+>", "", html.unescape(text)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "section"


def add_heading_ids(body):
    """Give plain <h2>/<h3> headings an id and a self-link; returns (body, [(id, text) of the h2 headings])."""
    used, toc = set(re.findall(r'\bid="([^"]+)"', body)) | {"content"}, []      # "content" is the page's own <main id>

    def repl(m):
        level, given, inner = m.group(1), re.search(r'id="([^"]*)"', m.group(2)), m.group(3)
        if given and given.group(1):
            ident = given.group(1)                                   # the author chose this address; keep it (links may rely on it)
        else:
            base = slugify(inner)
            ident, n = base, 2
            while ident in used:
                ident, n = f"{base}-{n}", n + 1
            used.add(ident)
        if level == "2":
            toc.append((ident, html.unescape(re.sub(r"<[^>]+>", "", inner))))
        if re.search(r"<a\b", inner, re.I):                       # a heading that already holds a link keeps it and gets no self-link
            return f'<h{level} id="{ident}">{inner}</h{level}>'
        return f'<h{level} id="{ident}"><a href="#{ident}">{inner}</a></h{level}>'
    return re.sub(r"<h([23])((?:\s+id=\"[^\"]*\")?)>(.*?)</h\1>", repl, body, flags=re.S), toc


def reading_minutes(body):
    text = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", body, flags=re.S | re.I)
    words = len(re.sub(r"<[^>]+>", " ", text).split())
    return max(1, round(words / 230))


# ---- rendering ----------------------------------------------------------------------------------------------------
def esc(text):
    return html.escape(text, quote=True)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"                # not strftime: that follows the machine's locale


def render(template, values):
    def sub(m):
        if m.group(1) not in values:
            raise BuildError(f"layout.html uses {{{{{m.group(1)}}}}} but the builder does not provide it")
        return values[m.group(1)]
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def nav_html(site, root, current):
    items = []
    for item in site["nav"]:
        href = safe_url(item["href"], "site.json nav")
        local = not re.match(r"([a-z][a-z0-9+.-]*:|#|/)", href, re.I)
        target = root + href if local else href
        page = re.sub(r"^(\./)+", "", href.split("#")[0].split("?")[0]).rstrip("/")
        cur = ' aria-current="page"' if local and page in (current, current + "/index.html") else ""
        items.append(f'<a href="{esc(target)}"{cur}>{esc(item["label"])}</a>')
    return "".join(items)


def theme_color(site):
    light = '<meta name="theme-color" content="#F5F4EF"'
    if not site["dark_mode"]:
        return light + ">"
    return f'{light} media="(prefers-color-scheme: light)"><meta name="theme-color" content="#17160F" media="(prefers-color-scheme: dark)">'


def footer_html(site):
    """The page footer: the site's own HTML, a default copyright line when left empty, nothing at all when "footer" is false."""
    if site["footer"] is False:
        return ""
    default = f"<p>&copy; {dt.date.today().year} {esc(site['author'])}</p>"
    return f'<footer class="credit">{site["footer"] or default}</footer>'


def page_html(site, template, *, title, description, root, main, current="", og_type="website", image="", canonical_path="", has_feed=False,
              styles=(), scripts=()):
    base = site["url"]
    og_extra, canonical = "", ""
    if image:
        img = image if re.match(r"[a-z]+://", image) else (f"{base}/{image}" if base else root + image)
        og_extra = f'<meta property="og:image" content="{esc(img)}">'
    if base:
        canonical = f'<link rel="canonical" href="{esc(base + "/" + canonical_path)}">'
    feed = f'<link rel="alternate" type="application/atom+xml" title="{esc(site["title"])}" href="{root}feed.xml">' if has_feed else ""
    full_title = title if title == site["title"] else f"{title} | {site['title']}"
    return render(template, {
        "lang": esc(site["lang"]), "scheme_attr": ' data-scheme="auto"' if site["dark_mode"] else "", "theme_color": theme_color(site), "title": esc(full_title), "description": esc(description or site["description"]),
        "og_type": og_type, "og_title": esc(title), "og_extra": og_extra, "canonical": canonical, "feed_link": feed,
        "twitter_card": "summary_large_image" if image else "summary", "root": root,
        "brand": esc(site["title"]), "nav": nav_html(site, root, current), "main": main,
        "head_extra": "".join(f'<link rel="stylesheet" href="{esc(x)}">' for x in styles),
        "scripts": "".join(f'<script src="{esc(x)}"></script>' for x in scripts),
        "footer": footer_html(site)})


def entry_main(site, e, publish, root_dir=ROOT, engine=None):
    body = expand_shortcodes(e["body"], Ctx(root_dir, "../", e["source"], engine))
    body = strip_draft_only(body) if publish else body
    body, toc = add_heading_ids(body)
    meta = []
    if e["date"]:
        meta += ["Published", fmt_date(e["date"])]
    if e["kind"] == "post":
        meta += ["Authors", authors_html(site, e)]
        section = next((s for s in site["sections"] if s["id"] == e["section"]), {})
        if section.get("reading_time", True):
            meta += ["Reading time", f"{reading_minutes(body)} min"]
    meta_html = '<div class="meta">' + "".join(f"<span>{v}</span>" for v in meta) + "</div>"
    draft = '<p><span class="pill butter">draft: not published</span></p>' if e["draft"] and not publish else ""
    links = ('<div class="btns">' + "".join(f'<a class="btn" href="{esc(u)}">{esc(l)}</a>' for l, u in e["links"]) + "</div>") if e["links"] else ""
    toc_html = ""
    if e["toc"] and toc:
        toc_html = '<nav class="toc" aria-label="On this page"><b>On this page</b><ol>' + "".join(
            f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc) + "</ol></nav>"
    return f"{draft}<h1>{esc(e['title'])}</h1>\n{meta_html}\n{links}\n{toc_html}\n{body}"


def author_names(site, e):
    """The authors of a post, in the order written: its `authors:` front matter, else the site's author."""
    return [n.strip() for n in (e["authors"] or site["author"]).split(",") if n.strip()]


def author_slug(name):
    """The address of an author's page: 'Zoë Q. Writer' becomes 'zoe-q-writer'."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def authors_html(site, e):
    """The value of the Authors row: plain text, or a link to each author's page when site.json sets "author_pages": true."""
    if not site["author_pages"]:
        return esc(e["authors"] or site["author"])
    return ", ".join(f'<a href="../authors/{author_slug(n)}/index.html">{esc(n)}</a>' for n in author_names(site, e))


def author_index(site, posts):
    """{address: (name, [posts, newest first])} for every author of these posts; two names that make the same address are an error."""
    found = {}
    for p in posts:
        for name in author_names(site, p):
            slug = author_slug(name)
            if not slug:
                raise BuildError(f"{p['source']}: the author '{name}' has no letters or digits to make an address from")
            known, items = found.setdefault(slug, (name, []))
            if known != name:
                raise BuildError(f"{p['source']}: the authors '{known}' and '{name}' would both live at authors/{slug}/; write the name the same way everywhere")
            if p not in items:
                items.append(p)
    return found


def author_groups(site, items):
    """An author's entries split by section, in site.json order, empty groups left out: [(anchor, heading, entries)].
    A site with no extra sections has one list, so there is nothing to tell apart and the caller shows it plain."""
    return [(anchor, heading, entries) for _, anchor, heading, entries in section_lists(site, items) if entries]


def author_main(site, name, items):
    """One author's page: their entries under a heading per section (Musings, Crosswords, ...) when the site has sections."""
    if not site["sections"]:
        return f"<h1>{esc(name)}</h1>\n{entry_list(items, '../../')}"
    groups = "\n".join(f'<h2 id="{anchor}">{esc(heading)}</h2>\n{entry_list(entries, "../../")}' for anchor, heading, entries in author_groups(site, items))
    return f"<h1>{esc(name)}</h1>\n{groups}"


def authors_main(site, authors):
    """The index of authors: a total per author, and with sections a breakdown under the name ("Musings 2 · Crosswords 1")."""
    rows = []
    for slug, (name, items) in sorted(authors.items(), key=lambda kv: kv[1][0].casefold()):
        detail = ""
        if site["sections"]:
            detail = "<p>" + " · ".join(f"{esc(heading)} {len(entries)}" for _, heading, entries in author_groups(site, items)) + "</p>"
        rows.append(f'<li class="entry"><span class="count">{len(items)} post{"" if len(items) == 1 else "s"}</span><div>'
                    f'<a class="title" href="{slug}/index.html">{esc(name)}</a>{detail}</div></li>')
    return "<h1>Authors</h1>\n" + ('<ul class="entries">' + "".join(rows) + "</ul>" if rows else "<p>Nothing published yet.</p>")


def entry_list(posts, root=""):
    items = []
    for p in posts:
        badge = ' <span class="pill butter">draft</span>' if p["draft"] else ""
        desc = f"<p>{esc(p['description'])}</p>" if p["description"] else ""
        items.append(f'<li class="entry"><time datetime="{p["date"].isoformat()}">{fmt_date(p["date"])}</time><div>'
                     f'<a class="title" href="{root}{p["slug"]}/index.html">{esc(p["title"])}</a>{badge}{desc}</div></li>')
    return '<ul class="entries">' + "".join(items) + "</ul>" if items else "<p>Nothing published yet.</p>"


def section_lists(site, posts):
    """[(page address, anchor on the home page, heading, entries)]: the main list first, then each extra section."""
    lists = [(site["posts_slug"], "posts", site["posts_heading"], [p for p in posts if not p["section"]])]
    lists += [(s["id"], s["id"], s["heading"], [p for p in posts if p["section"] == s["id"]]) for s in site["sections"]]
    return lists


def home_main(site, posts, publish, root_dir=ROOT, engine=None):
    """The overview: the intro, then every list (the main one under `posts_heading`, then one per extra section)."""
    intro = expand_shortcodes(site["intro"], Ctx(root_dir, "", "site.json (intro)", engine))
    parts = "\n".join(f'<h2 id="{anchor}">{esc(heading)}</h2>\n{entry_list(items)}' for _, anchor, heading, items in section_lists(site, posts))
    return f'<h1>{esc(site["title"])}</h1>\n<div class="lede">{intro}</div>\n{parts}'


def section_main(heading, items):
    """A page that shows only one section's entries."""
    return f"<h1>{esc(heading)}</h1>\n{entry_list(items, '../')}"


def atom_feed(site, posts):
    base = site["url"]
    updated = max(p["date"] for p in posts).isoformat() if posts else dt.date.today().isoformat()
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom">',
           f'<title>{esc(site["title"])}</title>', f'<id>{esc(base)}/</id>', f'<link href="{esc(base)}/"/>',
           f'<link rel="self" href="{esc(base)}/feed.xml"/>', f'<updated>{updated}T00:00:00Z</updated>',
           f'<author><name>{esc(site["author"])}</name></author>']
    for p in posts:
        url = f'{base}/{p["slug"]}/index.html'
        out += ["<entry>", f'<title>{esc(p["title"])}</title>', f'<id>{esc(url)}</id>', f'<link href="{esc(url)}"/>',
                f'<updated>{p["date"].isoformat()}T00:00:00Z</updated>', f'<summary>{esc(p["description"])}</summary>', "</entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def section_slugs(site):
    return [site["posts_slug"]] + [s["id"] for s in site["sections"]]


def sitemap(site, entries, extra=()):
    base = site["url"]
    urls = [f"{base}/index.html"] + [f'{base}/{s}/index.html' for s in section_slugs(site)] + [f'{base}/{x}' for x in extra] + [f'{base}/{e["slug"]}/index.html' for e in entries]
    return ('<?xml version="1.0" encoding="utf-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{esc(u)}</loc></url>\n" for u in urls) + "</urlset>\n")


# ---- the build ------------------------------------------------------------------------------------------------------------
def check_output_location(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out == root or out in root.parents:
        raise BuildError(f"{out} contains the site's sources; choose an output folder of its own (default: public/)")
    for part in ("content", "theme"):
        src = root / part
        if out == src or src in out.parents:
            raise BuildError(f"{out} is inside {part}/, which is copied into the output; choose another --out")


def prepare_output(out):
    if out.is_file():
        raise BuildError(f"{out} is a file; choose a folder for --out")
    if out.exists():
        entries = list(out.iterdir())
        if entries and not (out / MARKER).exists():
            raise BuildError(f"{out} exists and was not made by this tool; refusing to delete it (choose another --out)")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("generated by build.py; safe to delete\n", encoding="utf-8")


def build(root=ROOT, out=None, publish=False, engine=None):
    """Build the site in `root`; returns the list of files written (relative to the output folder). The theme, layout and
    built-in components come from `engine` (this tool's folder); any file under root/theme replaces the engine's file of the same name."""
    root, engine = Path(root), Path(engine) if engine else ENGINE
    out = Path(out) if out else root / "public"
    layout = root / "theme" / "layout.html"
    site = load_site(root)
    template = (layout if layout.exists() else engine / "theme" / "layout.html").read_text(encoding="utf-8")
    loaded = load_entries(root)
    entries = [e for e in loaded if not (publish and e["draft"])]
    known = {s["id"] for s in site["sections"]}
    for e in loaded:
        if e["section"] and e["section"] not in known:
            raise BuildError(f"{e['source']}: section '{e['section']}' is not listed under \"sections\" in site.json (known: {sorted(known) or 'none'})")
    for e in loaded:
        if site["author_pages"] and e["slug"] == "authors":
            raise BuildError(f"{e['source']}: the address 'authors' is used by the author pages (site.json \"author_pages\"); give the file another name or a slug")
        if e["slug"] in section_slugs(site):
            raise BuildError(f"{e['source']}: the address '{e['slug']}' is a section page (see site.json); give the file another name or a slug")
    posts = sorted((e for e in entries if e["kind"] == "post"), key=lambda e: (e["date"], e["slug"]), reverse=True)
    if site["author_pages"] and "authors" in section_slugs(site):
        raise BuildError("site.json: a section cannot use the address 'authors' while \"author_pages\" is on")
    authors = author_index(site, posts) if site["author_pages"] else {}
    check_output_location(root, out)
    prepare_output(out)
    has_feed = bool(site["url"])
    skip = shutil.ignore_patterns("layout.html", "components")
    shutil.copytree(engine / "theme", out / "theme", ignore=skip)
    if (root / "theme").is_dir() and (root / "theme").resolve() != (engine / "theme").resolve():
        shutil.copytree(root / "theme", out / "theme", ignore=skip, dirs_exist_ok=True)         # the site's own files win
    if (root / "content" / "images").exists():
        shutil.copytree(root / "content" / "images", out / "images")
    if not (out / "images" / "favicon.svg").exists():                  # the layout links it on every page
        (out / "images").mkdir(exist_ok=True)
        shutil.copy(engine / "content" / "images" / "favicon.svg", out / "images" / "favicon.svg")
    (out / "index.html").write_text(page_html(
        site, template, title=site["title"], description=site["description"], root="", current="index.html",
        main=home_main(site, posts, publish, root, engine), canonical_path="index.html", has_feed=has_feed), encoding="utf-8")
    for slug, _, heading, items in section_lists(site, posts):
        (out / slug).mkdir()
        (out / slug / "index.html").write_text(page_html(
            site, template, title=heading, description=site["description"], root="../", current=slug, main=section_main(heading, items),
            canonical_path=f"{slug}/index.html", has_feed=has_feed), encoding="utf-8")
    if site["author_pages"]:
        (out / "authors").mkdir()
        (out / "authors" / "index.html").write_text(page_html(
            site, template, title="Authors", description=site["description"], root="../", current="authors", main=authors_main(site, authors),
            canonical_path="authors/index.html", has_feed=has_feed), encoding="utf-8")
        for slug, (name, items) in authors.items():
            (out / "authors" / slug).mkdir()
            (out / "authors" / slug / "index.html").write_text(page_html(
                site, template, title=name, description=f"Posts by {name}", root="../../", current=f"authors/{slug}",
                main=author_main(site, name, items), canonical_path=f"authors/{slug}/index.html",
                has_feed=has_feed), encoding="utf-8")
    for e in entries:
        folder, own = out / e["slug"], e["source"].with_suffix("")
        if own.is_dir():                                           # content/posts/NAME/ : the page's own files (media, scripts, styles)
            if (own / "index.html").exists():
                raise BuildError(f"{own}: a page folder may not contain index.html (the page itself is {e['source'].name})")
            shutil.copytree(own, folder)
        else:
            folder.mkdir()
        (folder / "index.html").write_text(page_html(
            site, template, title=e["title"], description=e["description"], root="../", current=e["slug"],
            main=entry_main(site, e, publish, root, engine), og_type="article" if e["kind"] == "post" else "website", image=e["image"],
            canonical_path=f'{e["slug"]}/index.html', has_feed=has_feed,
            styles=e["styles"], scripts=e["scripts"]), encoding="utf-8")
    if has_feed:                                                    # drafts never go into the feed or the sitemap
        (out / "feed.xml").write_text(atom_feed(site, [p for p in posts if not p["draft"]]), encoding="utf-8")
        (out / "sitemap.xml").write_text(sitemap(site, [e for e in entries if not e["draft"]],
                                                         ["authors/index.html"] + [f"authors/{s}/index.html" for s in authors] if site["author_pages"] else ()), encoding="utf-8")
    else:
        print("note: site.json has no 'url', so feed.xml and sitemap.xml were not written (they need absolute addresses)")
    return sorted(str(p.relative_to(out)).replace("\\", "/") for p in out.rglob("*") if p.is_file())


# ---- checking the output ---------------------------------------------------------------------------------------------------
class RefCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for key in ("href", "src", "poster"):
            if a.get(key) and not (tag == "a" and key == "src"):
                self.refs.append((tag, a[key]))
        if a.get("srcset"):
            for candidate in a["srcset"].split(","):
                if candidate.split():
                    self.refs.append((tag, candidate.split()[0]))


def exists_exactly(out, target, listed):
    """True when `target` exists with exactly this spelling: a case-insensitive disk (Windows, macOS) would hide a 404 on a host that cares."""
    try:
        parts = Path(os.path.normpath(target)).relative_to(os.path.normpath(out)).parts
    except ValueError:
        return Path(target).exists()
    here = Path(os.path.normpath(out))
    for part in parts:
        if here not in listed:
            listed[here] = set(os.listdir(here)) if here.is_dir() else set()
        if part not in listed[here]:
            return False
        here = here / part
    return True


def check_links(out):
    """Problems in the built site: a link, image, script, stylesheet, font or #anchor that points at nothing."""
    out, problems, parsed, listed = Path(out), [], {}, {}

    def collect(path):
        if path not in parsed:
            c = RefCollector()
            c.feed(path.read_text(encoding="utf-8"))
            parsed[path] = c
        return parsed[path]
    for page in sorted(out.rglob("*.html")):
        for tag, ref in collect(page).refs:
            if re.match(r"([a-z][a-z0-9+.-]*:|//)", ref, re.I):
                continue                                                       # external, mailto:, data: ...
            path_part, _, frag = ref.partition("#")
            path_part, frag = unquote(path_part), unquote(frag)
            if path_part.startswith("/"):
                target = out / path_part.split("?")[0].lstrip("/")                    # a root-relative address starts at the site root
            else:
                target = page if not path_part else (page.parent / path_part.split("?")[0])
            if target.is_dir() or path_part.endswith("/"):
                target = target / "index.html"
            rel = page.relative_to(out)
            if not exists_exactly(out, target, listed):
                problems.append(f"{rel}: <{tag}> points at {ref!r}, which does not exist")
            elif frag and target.suffix == ".html" and frag not in collect(target).ids:
                problems.append(f"{rel}: {ref!r} has no element with id {frag!r}")
    for css in out.rglob("*.css"):
        for ref in re.findall(r"url\(([^)]+)\)", css.read_text(encoding="utf-8")):
            ref = ref.strip("\"'")
            if not re.match(r"(data:|https?:)", ref) and not (css.parent / ref).exists():
                problems.append(f"{css.relative_to(out)}: url({ref}) does not exist")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the blog into plain files.")
    ap.add_argument("--site", default=None, help="folder with site.json and content/ to build (default: this tool's own folder)")
    ap.add_argument("--out", default=None, help="output folder (default: public/ inside the site folder)")
    ap.add_argument("--publish", action="store_true", help="leave out drafts and draft-only notes")
    ap.add_argument("--check", action="store_true", help="after building, verify every link and file reference")
    a = ap.parse_args(argv)
    try:
        site_dir = Path(a.site).resolve() if a.site else ROOT
        files = build(site_dir, a.out, a.publish)
        out = Path(a.out) if a.out else site_dir / "public"
        print(f"built {len(files)} files into {out}" + (" (publish mode)" if a.publish else ""))
        if a.check:
            problems = check_links(out)
            for p in problems:
                print("broken:", p)
            if problems:
                return 1
            print("all links and file references resolve")
    except (BuildError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
