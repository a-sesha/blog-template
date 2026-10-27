"""Regression tests for the problems found in the code review of build.py."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402
from test_build import make_site, post  # noqa: E402


# ---- links -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["javascript:alert(1)", " JavaScript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)",
                                 "jav\x00ascript:x", "data:text/html,x", "vb\tscript:x"])
def test_a_dangerous_link_scheme_cannot_be_hidden_with_whitespace(url):
    with pytest.raises(B.BuildError, match="refusing the link"):
        B.safe_url(url, "f")


@pytest.mark.parametrize("url", ["https://a.example/x", "mailto:me@example.com", "../p/index.html", "#top", "about/index.html"])
def test_ordinary_links_are_accepted(url):
    assert B.safe_url(url, "f") == url


# ---- the draft stripper keeps everything it does not remove --------------------------------------------------------------------
@pytest.mark.parametrize("body", ['<svg><![CDATA[ a < b ]]></svg>', '<?xml version="1.0"?><p>x</p>', '<!DOCTYPE html><p>x</p>'])
def test_cdata_processing_instructions_and_doctypes_survive_stripping(body):
    assert B.strip_draft_only(body) == body


def test_stripping_removes_nested_notes_but_not_their_siblings():
    body = '<p>a</p><div class="x draft-only"><div>in<div class="draft-only">deeper</div></div>gone</div><p>b</p><ul><li>one</li></ul>'
    assert B.strip_draft_only(body) == '<p>a</p><p>b</p><ul><li>one</li></ul>'


# ---- headings ----------------------------------------------------------------------------------------------------------------
def test_toc_text_with_entities_is_not_escaped_twice(tmp_path):
    make_site(tmp_path, nav=[], posts={"a.html": post(body="<h2>Fish &amp; chips &lt;3</h2><p>x</p>", toc="true")})
    B.build(tmp_path, tmp_path / "out")
    toc = re.search(r'<nav class="toc".*?</nav>', (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8"), re.S).group(0)
    assert "Fish &amp; chips &lt;3" in toc and "&amp;amp;" not in toc


def test_a_heading_that_already_holds_a_link_gets_no_nested_self_link():
    body, toc = B.add_heading_ids('<h2>See <a href="https://x.example">the paper</a></h2>')
    assert body == '<h2 id="see-the-paper"><a>'.replace("<a>", "") + 'See <a href="https://x.example">the paper</a></h2>'
    assert body.count("<a ") == 1 and toc == [("see-the-paper", "See the paper")]


# ---- dates ------------------------------------------------------------------------------------------------------------------------
def test_dates_use_fixed_english_month_names_whatever_the_machine_language():
    assert [B.fmt_date(dt.date(2026, m, 1)) for m in (1, 3, 10, 12)] == ["1 Jan 2026", "1 Mar 2026", "1 Oct 2026", "1 Dec 2026"]
    assert B.fmt_date(dt.date(2026, 5, 31)) == "31 May 2026"


# ---- site.json -----------------------------------------------------------------------------------------------------------------------
def write_site(tmp, text):
    make_site(tmp)
    (tmp / "site.json").write_text(text, encoding="utf-8")


@pytest.mark.parametrize("text,msg", [
    ("{not json", "not valid JSON"),
    ("[1, 2]", "must contain a JSON object"),
    ('{"title": "T", "author": "A", "nav": [{"label": "x"}]}', "nav item 1"),
    ('{"title": "T", "author": "A", "nav": ["about"]}', "nav item 1"),
    ('{"title": "T", "author": "A", "url": "you.example"}', "must start with https://"),
])
def test_a_mistake_in_site_json_is_a_message(tmp_path, text, msg):
    write_site(tmp_path, text)
    with pytest.raises(B.BuildError, match=msg):
        B.build(tmp_path, tmp_path / "out")


def test_a_missing_site_json_is_a_message(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(B, "ROOT", tmp_path)
    assert B.main(["--out", str(tmp_path / "out")]) == 2 and "site.json" in capsys.readouterr().err


# ---- where the output may go -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("where", ["theme/x", "content/images/out", "theme", "content"])
def test_the_output_cannot_be_inside_the_folders_that_are_copied_into_it(tmp_path, where):
    make_site(tmp_path)
    with pytest.raises(B.BuildError, match="inside|sources"):
        B.build(tmp_path, tmp_path / where)


def test_the_output_cannot_be_the_site_folder_or_a_parent_of_it(tmp_path):
    make_site(tmp_path)
    for out in (tmp_path, tmp_path.parent):
        with pytest.raises(B.BuildError, match="contains the site's sources"):
            B.build(tmp_path, out)
    assert (tmp_path / "site.json").exists()                                      # nothing was deleted on the way


def test_the_output_may_not_be_an_existing_file(tmp_path):
    make_site(tmp_path)
    (tmp_path / "out").write_text("x", encoding="utf-8")
    with pytest.raises(B.BuildError, match="is a file"):
        B.build(tmp_path, tmp_path / "out")


def test_the_default_output_folder_is_allowed(tmp_path):
    make_site(tmp_path)
    B.build(tmp_path)
    assert (tmp_path / "public" / "index.html").exists()
