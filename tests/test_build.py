import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build as B  # noqa: E402


def make_site(tmp, posts=(), pages=(), **site_over):
    """A small site in tmp using the real theme. posts/pages: {filename: text}."""
    shutil.copytree(ROOT / "theme", tmp / "theme")
    site = {"title": "Test Blog", "author": "A. Writer", "url": "https://blog.example", "nav": [{"label": "About", "href": "about/index.html"}]}
    site.update(site_over)
    (tmp / "site.json").write_text(json.dumps(site), encoding="utf-8")
    for folder, items in (("posts", posts), ("pages", pages)):
        (tmp / "content" / folder).mkdir(parents=True)
        for name, text in dict(items).items():
            (tmp / "content" / folder / name).write_text(text, encoding="utf-8")
    (tmp / "content" / "images").mkdir()
    (tmp / "content" / "images" / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return tmp


def post(title="T", date="2026-02-03", body="<p>Hello</p>", **extra):
    fm = {"title": title, "date": date, **extra}
    return "---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n" + body


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """The shipped template, built as it is."""
    out = tmp_path_factory.mktemp("sample") / "public"
    B.build(ROOT, out)
    return out


# ---- the shipped template -----------------------------------------------------------------------------------------------
def test_the_shipped_template_builds_and_every_reference_resolves(sample):
    assert B.check_links(sample) == []
    assert (sample / "index.html").exists() and (sample / "components" / "index.html").exists() and (sample / "about" / "index.html").exists()
    assert not (sample / "theme" / "layout.html").exists()                       # the layout is a build input, not an output


def test_every_font_file_the_stylesheet_names_exists_in_the_theme():
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    fonts = re.findall(r"url\(([^)]+\.woff2)\)", css)
    assert len(fonts) == 6 and all((ROOT / "theme" / f).exists() for f in fonts)


def test_the_home_page_lists_posts_newest_first(sample):
    page = (sample / "index.html").read_text(encoding="utf-8")
    assert page.index("Every component in one place") < page.index("A first post, and how to replace it")
    assert 'href="components/index.html"' in page and "datetime=\"2026-01-16\"" in page


def test_the_shipped_site_has_no_url_so_no_feed_is_written_and_none_is_linked(sample):
    assert not (sample / "feed.xml").exists() and "alternate" not in (sample / "index.html").read_text(encoding="utf-8")


def test_the_page_skeleton_is_accessible(sample):
    page = (sample / "components" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in page and 'class="skip" href="#content"' in page and '<main id="content">' in page
    assert re.search(r"<title>Every component in one place \| Your Name</title>", page)
    assert page.count("<h1>") == 1 and 'aria-label="Main"' in page
    for svg in re.findall(r"<svg\b[^>]*>", page):
        assert 'role="img"' in svg and "aria-labelledby" in svg                  # every figure has a title and description


def test_no_page_has_duplicate_ids(sample):
    for page in sample.rglob("*.html"):
        ids = re.findall(r'\bid="([^"]+)"', page.read_text(encoding="utf-8"))
        assert len(ids) == len(set(ids)), (page, sorted({i for i in ids if ids.count(i) > 1}))


# ---- contrast: the rule written in the stylesheet, checked ---------------------------------------------------------------------
def luminance(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def token(name):
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    return re.search(rf"--{name}:\s*(#[0-9A-Fa-f]{{6}})", css).group(1)


@pytest.mark.parametrize("fg,bg,minimum", [("muted-2", "paper", 4.5), ("ink", "paper", 7), ("btn-ink", "btn", 4.5), ("ink", "butter", 7),
                                           ("muted-2", "greige", 4.0), ("ink", "teal", 7), ("ink", "sage", 7)])
def test_text_colour_pairs_are_readable(fg, bg, minimum):
    f = "#000000" if fg == "ink" else token(fg)
    assert contrast(f, token(bg)) >= minimum


def test_the_decorative_grey_is_not_used_for_text():
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    assert contrast(token("muted"), token("paper")) < 3                         # documented as decoration only
    assert not re.search(r"[;{]\s*color:\s*var\(--muted\)", css)                # ... and never set as a text colour


# ---- front matter ---------------------------------------------------------------------------------------------------------------
def test_front_matter_parses_and_tolerates_windows_line_endings_and_a_bom():
    text = "﻿---\r\ntitle: Hello: world\r\n# a comment\r\ndate: 2026-01-02\r\n---\r\n<p>x</p>\r\n"
    meta, body = B.parse_front_matter(text, "f")
    assert meta == {"title": "Hello: world", "date": "2026-01-02"} and body.strip() == "<p>x</p>"


@pytest.mark.parametrize("text,msg", [("no front matter", "front-matter block"), ("---\ntitle only\n---\nx", "key: value")])
def test_bad_front_matter_is_a_message(text, msg):
    with pytest.raises(B.BuildError, match=msg):
        B.parse_front_matter(text, "f")


@pytest.mark.parametrize("name,text,msg", [
    ("a.html", post(title=""), "title is required"),
    ("a.html", post(date="2026-13-40"), "YYYY-MM-DD"),
    ("a.html", "---\ntitle: x\n---\nbody", "YYYY-MM-DD"),                          # a post needs a date
    ("Bad Name.html", post(), "not a usable address"),
    ("theme.html", post(), "reserved"),
    ("a.html", post(links="Code | javascript:alert(1)"), "refusing the link"),
    ("a.html", post(links="Code https://x"), "Label | https"),
])
def test_content_errors_name_the_file_and_the_problem(tmp_path, name, text, msg):
    make_site(tmp_path, posts={name: text})
    with pytest.raises(B.BuildError, match=msg):
        B.build(tmp_path, tmp_path / "out")


def test_a_duplicate_address_is_refused(tmp_path):
    make_site(tmp_path, posts={"a.html": post()}, pages={"a.html": "---\ntitle: A page\n---\nx"})
    with pytest.raises(B.BuildError, match="already used"):
        B.build(tmp_path, tmp_path / "out")


def test_site_json_needs_a_title_and_an_author(tmp_path):
    make_site(tmp_path, title="")
    with pytest.raises(B.BuildError, match="'title' is required"):
        B.build(tmp_path, tmp_path / "out")


# ---- drafts and publish mode -----------------------------------------------------------------------------------------------------
DRAFT_BODY = '<p>keep</p><div class="draft-only"><b>note</b><div>inner <div>deep</div></div>SECRET-NOTE</div><p>after</p>'


def test_draft_only_elements_are_removed_from_the_source_in_publish_mode_and_shown_otherwise(tmp_path):
    make_site(tmp_path, posts={"a.html": post(body=DRAFT_BODY)})
    B.build(tmp_path, tmp_path / "dev")
    B.build(tmp_path, tmp_path / "pub", publish=True)
    assert "SECRET-NOTE" in (tmp_path / "dev" / "a" / "index.html").read_text(encoding="utf-8")
    pub = (tmp_path / "pub" / "a" / "index.html").read_text(encoding="utf-8")
    assert "SECRET-NOTE" not in pub and "draft-only" not in pub.replace(".draft-only", "") and "<p>keep</p>" in pub and "<p>after</p>" in pub


@pytest.mark.parametrize("body", ['<p>a &amp; b &copy; &#169;</p><!-- keep me --><img src="x.png" alt=""><br/><p>z</p>',
                                  '<pre><code>if a &lt; b: pass</code></pre><svg viewBox="0 0 1 1"><path d="M0 0"/></svg>'])
def test_stripping_leaves_everything_else_exactly_as_written(body):
    assert B.strip_draft_only(body) == body


def test_a_draft_post_is_a_badge_in_dev_and_absent_from_publish_feed_and_sitemap(tmp_path):
    make_site(tmp_path, posts={"live.html": post("Live", "2026-01-02"), "wip.html": post("Work in progress", "2026-03-04", draft="true")})
    B.build(tmp_path, tmp_path / "dev")
    dev = (tmp_path / "dev" / "index.html").read_text(encoding="utf-8")
    assert "Work in progress" in dev and "draft</span>" in dev and (tmp_path / "dev" / "wip" / "index.html").exists()
    assert "Work in progress" not in (tmp_path / "dev" / "feed.xml").read_text(encoding="utf-8")                # never in the feed
    assert "wip" not in (tmp_path / "dev" / "sitemap.xml").read_text(encoding="utf-8")
    B.build(tmp_path, tmp_path / "pub", publish=True)
    assert not (tmp_path / "pub" / "wip").exists() and "Work in progress" not in (tmp_path / "pub" / "index.html").read_text(encoding="utf-8")


# ---- page content ------------------------------------------------------------------------------------------------------------------
def test_headings_get_unique_ids_and_a_table_of_contents(tmp_path):
    body = "<h2>Same name</h2><p>x</p><h2>Same name</h2><h3>Sub <code>part</code></h3><h2 id=\"mine\">Own id</h2>"
    make_site(tmp_path, posts={"a.html": post(body=body, toc="true")})
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert '<h2 id="same-name">' in page and '<h2 id="same-name-2">' in page and '<h3 id="sub-part">' in page
    assert 'id="mine"' in page and page.count('id="mine"') == 1
    toc = re.search(r'<nav class="toc".*?</nav>', page, re.S).group(0)
    assert toc.count("<li>") == 3 and 'href="#same-name-2"' in toc and 'href="#mine"' in toc and "Sub" not in toc    # h2 only; own ids kept


def test_reading_time_ignores_markup_scripts_and_svg():
    words = "<p>" + "word " * 460 + "</p>"
    assert B.reading_minutes(words) == 2
    assert B.reading_minutes(words + "<svg>" + "x " * 5000 + "</svg><script>" + "y " * 5000 + "</script>") == 2
    assert B.reading_minutes("<p>short</p>") == 1


def test_titles_and_descriptions_are_escaped_everywhere(tmp_path):
    nasty = 'Fish & "Chips" <script>alert(1)</script>'
    make_site(tmp_path, posts={"a.html": post(nasty, description=nasty, tags=nasty, authors=nasty)})
    B.build(tmp_path, tmp_path / "out")
    for f in ("index.html", "a/index.html", "feed.xml"):
        text = (tmp_path / "out" / f).read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in text, f
    ET.parse(tmp_path / "out" / "feed.xml")                                           # still well-formed XML
    assert "Fish &amp; &quot;Chips&quot;" in (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")


def test_the_header_block_shows_date_authors_reading_time_tags_and_links(tmp_path):
    make_site(tmp_path, posts={"a.html": post(tags="x, y", links="Code | https://c.example; Paper | ../p/index.html", authors="B. Coauthor")})
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert "<span>3 Feb 2026</span>" in page and "B. Coauthor" in page and "1 min" in page
    assert page.count('class="pill"') == 2 and 'class="btn" href="https://c.example">Code' in page and 'href="../p/index.html">Paper' in page


def test_pages_have_no_date_or_reading_time_and_are_not_listed(tmp_path):
    make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": "---\ntitle: About\n---\n<p>me</p>"})
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "about" / "index.html").read_text(encoding="utf-8")
    assert "Published" not in page and "Reading time" not in page
    assert "about/index.html" not in (tmp_path / "out" / "index.html").read_text(encoding="utf-8").split('<h2 id="posts">')[1]


# ---- links between pages -----------------------------------------------------------------------------------------------------------
def test_relative_paths_are_right_at_every_depth_so_the_site_works_from_a_folder_on_disk(tmp_path):
    make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": "---\ntitle: About\n---\nx"})
    B.build(tmp_path, tmp_path / "out")
    home = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    deep = (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert 'href="theme/style.css"' in home and 'href="../theme/style.css"' in deep
    assert 'href="a/index.html"' in home and 'href="../about/index.html"' in deep and 'href="../index.html"' in deep
    assert B.check_links(tmp_path / "out") == []


def test_the_current_page_is_marked_in_the_navigation(tmp_path):
    make_site(tmp_path, pages={"about.html": "---\ntitle: About\n---\nx"})
    B.build(tmp_path, tmp_path / "out")
    assert 'aria-current="page"' in (tmp_path / "out" / "about" / "index.html").read_text(encoding="utf-8")
    assert 'aria-current="page"' not in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_the_link_checker_finds_what_is_broken(tmp_path):
    make_site(tmp_path, posts={"a.html": post(body='<a href="../nope/index.html">x</a><a href="#missing">y</a><img src="../images/none.png" alt="">'
                                                   '<a href="https://elsewhere.example/x">fine</a><a href="mailto:me@example.com">fine</a>')})
    B.build(tmp_path, tmp_path / "out")
    problems = "\n".join(B.check_links(tmp_path / "out"))
    assert "nope/index.html" in problems and "'#missing'" in problems and "none.png" in problems
    assert "elsewhere" not in problems and "mailto" not in problems
    (tmp_path / "out" / "theme" / "fonts" / "source-sans-3-latin-400-normal.woff2").unlink()
    assert "url(fonts/source-sans-3-latin-400-normal.woff2)" in "\n".join(B.check_links(tmp_path / "out"))


# ---- feed and sitemap -----------------------------------------------------------------------------------------------------------------
def test_feed_and_sitemap_are_valid_xml_with_absolute_addresses_newest_first(tmp_path):
    make_site(tmp_path, posts={"old.html": post("Old", "2025-01-01"), "new.html": post("New", "2026-05-06", description="Fresh")})
    B.build(tmp_path, tmp_path / "out")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    feed = ET.parse(tmp_path / "out" / "feed.xml").getroot()
    assert [e.find("a:title", ns).text for e in feed.findall("a:entry", ns)] == ["New", "Old"]
    assert feed.find("a:entry/a:link", ns).get("href") == "https://blog.example/new/index.html"
    assert feed.find("a:updated", ns).text == "2026-05-06T00:00:00Z"
    urls = [u.text for u in ET.parse(tmp_path / "out" / "sitemap.xml").getroot().iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    assert "https://blog.example/index.html" in urls and "https://blog.example/old/index.html" in urls
    home = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert 'rel="alternate" type="application/atom+xml"' in home and 'rel="canonical" href="https://blog.example/index.html"' in home


def test_an_empty_blog_still_builds(tmp_path):
    make_site(tmp_path)
    B.build(tmp_path, tmp_path / "out")
    assert "Nothing published yet" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    ET.parse(tmp_path / "out" / "feed.xml")


def test_the_link_preview_image_is_absolute_when_the_site_has_an_address(tmp_path):
    make_site(tmp_path, posts={"a.html": post(image="images/pic.png")})
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert '<meta property="og:image" content="https://blog.example/images/pic.png">' in page and "summary_large_image" in page


# ---- the output folder -----------------------------------------------------------------------------------------------------------------
def test_the_build_refuses_to_clear_a_folder_it_did_not_make(tmp_path):
    make_site(tmp_path)
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "thesis.docx").write_text("do not delete", encoding="utf-8")
    with pytest.raises(B.BuildError, match="not made by this tool"):
        B.build(tmp_path, precious)
    assert (precious / "thesis.docx").exists()


def test_rebuilding_replaces_the_previous_output(tmp_path):
    make_site(tmp_path, posts={"a.html": post()})
    B.build(tmp_path, tmp_path / "out")
    (tmp_path / "content" / "posts" / "a.html").unlink()
    B.build(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out" / "a").exists()


def test_command_line_reports_errors_without_a_traceback(tmp_path, capsys, monkeypatch):
    make_site(tmp_path, posts={"a.html": post(date="soon")}, pages={"about.html": "---\ntitle: About\n---\nx"})
    monkeypatch.setattr(B, "ROOT", tmp_path)
    assert B.main(["--out", str(tmp_path / "out")]) == 2 and "error:" in capsys.readouterr().err
    (tmp_path / "content" / "posts" / "a.html").write_text(post(), encoding="utf-8")
    assert B.main(["--out", str(tmp_path / "out"), "--check", "--publish"]) == 0
    assert "publish mode" in capsys.readouterr().out


def test_only_the_labels_of_the_header_block_are_grey_not_the_tag_pills_inside_a_value():
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    assert ".meta>span:nth-child(odd){" in css and ".meta span:nth-child(odd)" not in css
