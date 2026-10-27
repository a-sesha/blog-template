"""A post may bring its own folder (media, data, scripts, styles): content/posts/NAME.html + content/posts/NAME/."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402
from test_build import make_site, post  # noqa: E402


def with_folder(tmp, files, **front):
    make_site(tmp, nav=[], posts={"trail.html": post(body='<p>x</p><video src="assets/clip.mp4"></video>', **front)})
    folder = tmp / "content" / "posts" / "trail"
    for rel, text in files.items():
        f = folder / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")


def test_the_pages_folder_is_published_next_to_the_page_with_relative_links_intact(tmp_path):
    with_folder(tmp_path, {"assets/clip.mp4": "video", "data.js": "var d=1;"})
    B.build(tmp_path, tmp_path / "out")
    assert (tmp_path / "out" / "trail" / "assets" / "clip.mp4").read_text() == "video" and (tmp_path / "out" / "trail" / "data.js").exists()
    assert B.check_links(tmp_path / "out") == []                                      # src="assets/clip.mp4" resolves from the page


def test_a_missing_file_in_the_folder_is_found_by_the_checker(tmp_path):
    with_folder(tmp_path, {"other.txt": "x"})
    B.build(tmp_path, tmp_path / "out")
    assert any("assets/clip.mp4" in p for p in B.check_links(tmp_path / "out"))


def test_a_folder_may_not_replace_the_page_itself(tmp_path):
    with_folder(tmp_path, {"index.html": "<p>sneaky</p>"})
    with pytest.raises(B.BuildError, match="may not contain index.html"):
        B.build(tmp_path, tmp_path / "out")


def test_a_post_without_a_folder_still_works_and_other_posts_do_not_get_the_files(tmp_path):
    make_site(tmp_path, posts={"a.html": post(), "b.html": post()})
    (tmp_path / "content" / "posts" / "b").mkdir()
    (tmp_path / "content" / "posts" / "b" / "only-b.txt").write_text("b", encoding="utf-8")
    B.build(tmp_path, tmp_path / "out")
    assert (tmp_path / "out" / "b" / "only-b.txt").exists() and not (tmp_path / "out" / "a" / "only-b.txt").exists()


def test_styles_and_scripts_are_linked_in_order_after_the_theme(tmp_path):
    with_folder(tmp_path, {"assets/clip.mp4": "v", "one.css": "p{}", "two.css": "p{}", "a.js": "1", "b.js": "2"}, styles="one.css, two.css", scripts="a.js?v=3, b.js")
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "trail" / "index.html").read_text(encoding="utf-8")
    css = [m for m in re.findall(r'<link rel="stylesheet" href="([^"]+)"', page)]
    assert css == ["../theme/style.css", "one.css", "two.css"]                       # the page's own styles win over the theme
    js = re.findall(r'<script src="([^"]+)"', page)
    assert js == ["a.js?v=3", "b.js", "../theme/theme.js"]
    assert B.check_links(tmp_path / "out") == []
    home = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    assert "one.css" not in home and "a.js" not in home                              # other pages do not load this page's files


def test_a_listed_script_that_is_missing_is_reported(tmp_path):
    with_folder(tmp_path, {}, scripts="gone.js")
    B.build(tmp_path, tmp_path / "out")
    assert any("gone.js" in p for p in B.check_links(tmp_path / "out"))


@pytest.mark.parametrize("bad", ["../x.js", "/x.js", "https://evil.example/x.js", "javascript:alert(1)", "a/../../x.js", "\\x.js"])
def test_styles_and_scripts_cannot_point_outside_the_pages_folder(tmp_path, bad):
    make_site(tmp_path, posts={"a.html": post(scripts=bad)})
    with pytest.raises(B.BuildError, match="own folder"):
        B.build(tmp_path, tmp_path / "out")


def test_headings_with_their_own_ids_keep_them_and_join_the_table_of_contents(tmp_path):
    body = '<h2 id="setup">The setup</h2><p>a</p><h2 id="results">Results</h2><h3 id="sub">Sub</h3><h2>No id</h2>'
    make_site(tmp_path, nav=[], posts={"a.html": post(body=body, toc="true")})
    B.build(tmp_path, tmp_path / "out")
    page = (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert '<h2 id="setup"><a href="#setup">The setup</a></h2>' in page and '<h3 id="sub">' in page
    toc = re.search(r'<nav class="toc".*?</nav>', page, re.S).group(0)
    assert [m for m in re.findall(r'href="#([^"]+)"', toc)] == ["setup", "results", "no-id"]
    assert B.check_links(tmp_path / "out") == []
