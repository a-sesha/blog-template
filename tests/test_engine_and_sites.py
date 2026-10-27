"""One engine, several sites: a folder with only site.json and content/ is built with this tool's theme, layout and pieces."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402


def bare_site(tmp, body="<p>Hello</p>", nav=()):
    """A site with no theme of its own."""
    (tmp / "content" / "posts").mkdir(parents=True)
    (tmp / "content" / "images").mkdir()
    (tmp / "content" / "images" / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp / "site.json").write_text(json.dumps({"title": "My Site", "author": "Me", "url": "https://me.example", "nav": list(nav)}), encoding="utf-8")
    (tmp / "content" / "posts" / "a.html").write_text(f"---\ntitle: A\ndate: 2026-01-02\n---\n{body}", encoding="utf-8")
    return tmp


def listing(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*") if "__pycache__" not in p.parts and ".pytest_cache" not in p.parts)


def test_a_site_without_a_theme_is_built_with_the_engines_theme(tmp_path):
    site = bare_site(tmp_path / "site")
    B.build(site, site / "public")
    out = site / "public"
    assert (out / "theme" / "style.css").exists() and (out / "theme" / "theme.js").exists()
    assert len(list((out / "theme" / "fonts").glob("*.woff2"))) == 6
    assert not (out / "theme" / "layout.html").exists() and not (out / "theme" / "components").exists()
    assert B.check_links(out) == []


def test_building_a_site_never_writes_into_the_engine_folder(tmp_path):
    before = listing(B.ENGINE)
    site = bare_site(tmp_path / "site")
    B.build(site, site / "public")
    assert listing(B.ENGINE) == before


def test_a_site_theme_file_replaces_the_engines_and_the_rest_is_kept(tmp_path):
    site = bare_site(tmp_path / "site")
    (site / "theme").mkdir()
    (site / "theme" / "style.css").write_text("/* MY SKIN */ body{color:red}", encoding="utf-8")
    B.build(site, site / "public")
    css = (site / "public" / "theme" / "style.css").read_text(encoding="utf-8")
    assert "MY SKIN" in css and "paper" not in css
    assert (site / "public" / "theme" / "theme.js").exists() and len(list((site / "public" / "theme" / "fonts").glob("*.woff2"))) == 6


def test_a_site_can_bring_its_own_layout(tmp_path):
    site = bare_site(tmp_path / "site")
    (site / "theme").mkdir()
    layout = (B.ENGINE / "theme" / "layout.html").read_text(encoding="utf-8").replace("<main", '<div id="mine"></div><main')
    (site / "theme" / "layout.html").write_text(layout, encoding="utf-8")
    B.build(site, site / "public")
    assert 'id="mine"' in (site / "public" / "a" / "index.html").read_text(encoding="utf-8")


def test_pieces_are_looked_up_in_the_site_first_then_its_theme_then_the_engine(tmp_path):
    site = bare_site(tmp_path / "site", body="{{pill x}}")
    page = lambda: (site / "public" / "a" / "index.html").read_text(encoding="utf-8")
    B.build(site, site / "public")
    assert '<span class="pill ">x</span>' in page()                                   # the engine's
    (site / "theme" / "components").mkdir(parents=True)
    (site / "theme" / "components" / "pill.html").write_text("<i>theme {{1}}</i>", encoding="utf-8")
    B.build(site, site / "public")
    assert "<i>theme x</i>" in page()                                                # the site's theme beats the engine
    (site / "content" / "snippets").mkdir()
    (site / "content" / "snippets" / "pill.html").write_text("<b>content {{1}}</b>", encoding="utf-8")
    B.build(site, site / "public")
    assert "<b>content x</b>" in page()                                              # the site's content beats both


def test_the_unknown_piece_message_lists_pieces_from_every_place(tmp_path):
    site = bare_site(tmp_path / "site", body="{{nope}}")
    (site / "content" / "snippets").mkdir()
    (site / "content" / "snippets" / "mine.html").write_text("<p>x</p>", encoding="utf-8")
    with pytest.raises(B.BuildError, match="available: .*callout.*mine|available: .*mine.*callout"):
        B.build(site, site / "public")


def test_the_command_line_builds_another_folder_next_to_that_folder(tmp_path, capsys):
    site = bare_site(tmp_path / "site", nav=[{"label": "Home", "href": "index.html"}])
    assert B.main(["--site", str(site), "--check"]) == 0
    assert (site / "public" / "index.html").exists() and "built" in capsys.readouterr().out
    assert not (B.ENGINE / "public" / "a").exists()


def test_a_site_folder_without_site_json_is_a_message(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert B.main(["--site", str(tmp_path / "empty")]) == 2
    assert "site.json" in capsys.readouterr().err


def test_publish_and_check_work_for_a_separate_site(tmp_path, capsys):
    site = bare_site(tmp_path / "site", body='<p>x</p><div class="draft-only">SECRET</div>')
    assert B.main(["--site", str(site), "--publish", "--check", "--out", str(tmp_path / "dist")]) == 0
    assert "SECRET" not in (tmp_path / "dist" / "a" / "index.html").read_text(encoding="utf-8")
    assert "publish mode" in capsys.readouterr().out
