"""Mistakes an author can make (bad encodings, typos in flags, odd puzzles, links that could escape) and how the build answers: a message, never a
traceback, and never a published draft."""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import B, ROOT, make_site, post  # noqa: E402
from test_crossword import RING, ipuz, write  # noqa: E402

ABOUT = "---\ntitle: About\n---\n<p>x</p>"


def build(site, **kw):
    out = site / "public"
    B.build(site, out, **kw)
    return out


# ---- files and flags ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw", ["draft: on", "draft: enabled", "draft: ON ", "draft: x", "draft: drafts"])
def test_a_draft_flag_that_is_not_clearly_yes_or_no_is_an_error_not_a_published_draft(tmp_path, raw):
    site = make_site(tmp_path, posts={"a.html": "---\ntitle: A\ndate: 2026-01-01\n" + raw + "\n---\n<p>secret</p>"}, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError, match="'draft' must be true or false"):
        build(site, publish=True)


@pytest.mark.parametrize("raw,expected", [("true", True), ("Yes", True), ("1", True), ("no", False), ("false", False), ("", False)])
def test_the_clear_flag_words_still_work(tmp_path, raw, expected):
    meta, _ = B.parse_front_matter(f"---\ntitle: A\ndraft: {raw}\n---\nx", "f")
    assert B.parse_bool(meta, "draft", "f") is expected


def test_toc_gets_the_same_strictness(tmp_path):
    site = make_site(tmp_path, posts={"a.html": "---\ntitle: A\ndate: 2026-01-01\ntoc: maybe\n---\n<p>x</p>"}, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError, match="'toc' must be true or false"):
        build(site)


def test_a_file_that_is_not_utf8_is_a_message_naming_it(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    (site / "content" / "posts" / "bad.html").write_bytes("---\ntitle: B\ndate: 2026-01-01\n---\n<p>é</p>".encode("utf-16"))
    with pytest.raises(B.BuildError, match=r"bad\.html: not UTF-8 text"):
        build(site)
    assert B.main(["--site", str(site), "--out", str(tmp_path / "o")]) == 2                       # and through the command line: a message, not a crash


def test_a_bom_in_site_json_snippets_and_svgs_is_ignored(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(body="<p>{{note}}</p>{{svg dot.svg}}")}, pages={"about.html": ABOUT})
    (site / "site.json").write_text("\ufeff" + (site / "site.json").read_text(encoding="utf-8"), encoding="utf-8")
    (site / "content" / "snippets").mkdir()
    (site / "content" / "snippets" / "note.html").write_text("\ufeff<b>noted</b>", encoding="utf-8")
    (site / "content" / "images" / "dot.svg").write_text('\ufeff<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>', encoding="utf-8")
    page = (build(site) / "a" / "index.html").read_text(encoding="utf-8")
    assert "<b>noted</b>" in page and "<circle" in page and "\ufeff" not in page


@pytest.mark.parametrize("date", ["20261026", "2026-W43-1", "2026-1-2"])
def test_only_yyyy_mm_dd_is_a_date_on_every_python_version(tmp_path, date):
    site = make_site(tmp_path, posts={"a.html": post(date=date)}, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError, match="date must be written YYYY-MM-DD"):
        build(site)


def test_an_unclosed_draft_only_element_is_an_error_when_publishing_not_a_silently_cut_page(tmp_path):
    body = '<p>keep</p><p class="draft-only">note<p>after</p><p>more</p>'
    site = make_site(tmp_path, posts={"a.html": post(body=body)}, pages={"about.html": ABOUT})
    build(site)                                                    # fine while working: the note is just shown
    with pytest.raises(B.BuildError, match=r'class="draft-only" <p> is never closed'):
        build(site, publish=True)


# ---- addresses ----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["con", "nul", "com1", "lpt9", "aux"])
def test_windows_device_names_are_not_addresses(tmp_path, name):
    site = make_site(tmp_path, posts={f"{name}.html": post()}, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError, match="not a usable address"):
        build(site)
    with pytest.raises(B.BuildError, match="not a usable section address"):
        B.load_site(make_site(tmp_path / "s", sections=[{"id": name, "heading": "X"}]))


def test_an_author_named_like_a_windows_device_is_refused(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(authors="CON")}, author_pages=True, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError, match="no usable address"):
        build(site)


# ---- puzzles ------------------------------------------------------------------------------------------------------------------------------------
def read(tmp, doc, name="p.ipuz"):
    return B.read_ipuz(write(tmp, doc, name), "post.html")


@pytest.mark.parametrize("solution,match", [
    (["AB", "Cß"], "no rebus"), (["ßB", "CD"], "no rebus"), (["AÉ", "CD"], "no rebus"), (["A²", "CD"], "no rebus"),
])
def test_only_ascii_letters_and_digits_are_squares_so_every_puzzle_can_be_typed(tmp_path, solution, match):
    doc = ipuz(["AB", "CD"], {1: "x", 3: "y"}, {1: "z", 2: "w"})
    doc["solution"] = [list(row) for row in solution]
    with pytest.raises(B.BuildError, match=match):
        read(tmp_path, doc)


def test_a_square_in_no_word_and_a_grid_with_no_words_are_messages(tmp_path):
    lone = ipuz(["AB#", "CD#", "##E"], {1: "x", 3: "y"}, {1: "z", 2: "w"})
    with pytest.raises(B.BuildError, match="row 3, column 3 is in no word"):
        read(tmp_path, lone)
    (tmp_path / "n").mkdir()
    with pytest.raises(B.BuildError, match="no words"):
        read(tmp_path / "n", ipuz(["A#", "#B"], {}, {}))


def test_a_puzzle_without_answers_says_so_and_other_ipuz_kinds_are_not_played_as_crosswords(tmp_path):
    doc = json.loads(json.dumps(RING))
    del doc["solution"]
    with pytest.raises(B.BuildError, match='has no "solution" grid'):
        read(tmp_path, doc)
    for kind in (["http://ipuz.org/crossword/arrowword#1"], ["http://ipuz.org/sudoku#1"], []):
        doc = json.loads(json.dumps(RING))
        doc["kind"] = kind
        with pytest.raises(B.BuildError, match="is not an ipuz crossword"):
            read(tmp_path, doc, "k.ipuz")
    doc = json.loads(json.dumps(RING))
    doc["kind"] = "http://ipuz.org/crossword#2"                    # a bare string is accepted, and so is version 2
    assert read(tmp_path, doc, "k2.ipuz")["title"] == "Ring"


@pytest.mark.parametrize("edit", [lambda d: d.update(dimensions={"width": 1e999, "height": 3}), lambda d: d["clues"]["Across"].__setitem__(0, [True, "x"]),
                                  lambda d: d["clues"]["Across"].__setitem__(0, [1e999, "x"])])
def test_odd_numbers_in_a_puzzle_are_messages_not_tracebacks(tmp_path, edit):
    doc = json.loads(json.dumps(RING).replace("Infinity", "1e999"))
    edit(doc)
    text = json.dumps(doc).replace("Infinity", "1e999")
    with pytest.raises(B.BuildError):
        read(tmp_path, text)


def test_progress_is_saved_per_page_so_the_same_grid_on_two_pages_does_not_share_it(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(body="{{crossword p.ipuz}}"), "b.html": post(title="B", body="{{crossword p.ipuz}}")}, pages={"about.html": ABOUT})
    for slug in ("a", "b"):
        (site / "content" / "posts" / slug).mkdir()
        write(site / "content" / "posts" / slug, RING)
    out = build(site)
    ids = [re.search(r'data-id="([0-9a-f]{12})"', (out / s / "index.html").read_text(encoding="utf-8")).group(1) for s in ("a", "b")]
    assert ids[0] != ids[1]


def test_two_puzzles_on_one_page_both_render_and_the_script_may_load_twice_without_harm(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(body="{{crossword p.ipuz}}{{crossword q.ipuz}}")}, pages={"about.html": ABOUT})
    folder = site / "content" / "posts" / "a"
    folder.mkdir()
    write(folder, RING, "p.ipuz")
    write(folder, ipuz(["AB", "CD"], {1: "x", 3: "y"}, {1: "z", 2: "w"}), "q.ipuz")
    page = (build(site) / "a" / "index.html").read_text(encoding="utf-8")
    assert page.count('class="crossword wide"') == 2
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    assert "if (window.blogCrosswordLoaded) return;" in js         # a second copy of the script does nothing, so boards start once


# ---- links, symlinks, feeds ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("href", ["javascript:alert(1)", "JaVa\tScRiPt:alert(1)", "data:text/html,x", "vbscript:x"])
def test_button_and_chip_links_get_the_same_safe_url_check_as_nav_and_links(tmp_path, href):
    site = make_site(tmp_path, posts={"a.html": post(body=f'{{{{button href="{href}" text="x"}}}}')}, pages={"about.html": ABOUT})
    with pytest.raises(B.BuildError):
        build(site)


def test_a_control_character_in_a_title_cannot_make_the_feed_unreadable(tmp_path):
    import xml.etree.ElementTree as ET
    site = make_site(tmp_path, posts={"a.html": post(title="bad\x0bchar", description="a\x00b")}, pages={"about.html": ABOUT})
    ET.parse(build(site) / "feed.xml")


def test_a_symbolic_link_in_a_post_folder_or_the_images_is_refused(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    secret = tmp_path / "secret.txt"
    secret.write_text("private", encoding="utf-8")
    (site / "content" / "posts" / "a").mkdir()
    try:
        os.symlink(secret, site / "content" / "posts" / "a" / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("this account may not create symbolic links")
    with pytest.raises(B.BuildError, match="is a symbolic link"):
        build(site)


def test_dotfiles_in_a_post_folder_are_not_published(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    (site / "content" / "posts" / "a").mkdir()
    (site / "content" / "posts" / "a" / ".DS_Store").write_text("x", encoding="utf-8")
    (site / "content" / "posts" / "a" / "clip.txt").write_text("x", encoding="utf-8")
    out = build(site)
    assert (out / "a" / "clip.txt").exists() and not (out / "a" / ".DS_Store").exists()


# ---- the output folder ------------------------------------------------------------------------------------------------------------------------------
def test_a_mistake_found_while_rendering_leaves_the_previous_output_alone(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    out = build(site)
    before = (out / "index.html").read_text(encoding="utf-8")
    (site / "content" / "posts" / "b.html").write_text(post(title="B", body="{{nosuchpiece}}"), encoding="utf-8")
    with pytest.raises(B.BuildError, match="nosuchpiece"):
        build(site)
    assert (out / "index.html").read_text(encoding="utf-8") == before and (out / "a" / "index.html").exists()


def test_a_page_folder_with_its_own_index_html_is_caught_before_anything_is_written(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    out = build(site)
    (site / "content" / "posts" / "a").mkdir()
    (site / "content" / "posts" / "a" / "index.html").write_text("x", encoding="utf-8")
    with pytest.raises(B.BuildError, match="may not contain index.html"):
        build(site)
    assert (out / "a" / "index.html").exists()


def test_the_engines_own_theme_folder_is_not_an_output_folder(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    scratch = ROOT / "theme" / "scratch-out"
    try:
        with pytest.raises(B.BuildError, match="is inside theme/"):
            B.build(site, scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)                                                  # (nothing should exist; belt and braces)


# ---- cache busting and the link checker ------------------------------------------------------------------------------------------------------------
def test_theme_files_carry_a_version_that_follows_their_content(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    first = (build(site) / "index.html").read_text(encoding="utf-8")
    again = (build(site) / "index.html").read_text(encoding="utf-8")
    assert first == again
    stamp = re.search(r'theme/style\.css\?v=([0-9a-f]{8})"', first).group(1)
    (site / "theme" / "style.css").write_text((site / "theme" / "style.css").read_text(encoding="utf-8") + "\n/* changed */", encoding="utf-8")
    assert re.search(r'theme/style\.css\?v=([0-9a-f]{8})"', (build(site) / "index.html").read_text(encoding="utf-8")).group(1) != stamp


def test_every_page_gets_the_same_version_for_the_same_file_and_the_fonts_are_left_alone(tmp_path):
    out = build(make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT}))
    versions = {re.search(r"style\.css\?v=([0-9a-f]{8})", (out / p).read_text(encoding="utf-8")).group(1) for p in ("index.html", "a/index.html", "about/index.html")}
    assert len(versions) == 1
    assert 'fonts/source-sans-3-latin-400-normal.woff2" as=' in (out / "index.html").read_text(encoding="utf-8")


def test_css_urls_that_are_not_files_are_not_reported(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (out / "f.woff2").write_bytes(b"x")
    (out / "s.css").write_text("a{background:url(#blur)}b{background:url(//cdn.example/x.png)}c{src:url(f.woff2?v=1)}d{background:url(/abs.png)}e{background:url(gone.png)}", encoding="utf-8")
    problems = B.check_links(out)
    assert len(problems) == 1 and "gone.png" in problems[0]
