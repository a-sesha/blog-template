import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import B, ROOT, contrast, luminance, make_site, post  # noqa: E402

CSS = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")


def dark_tokens():
    block = re.search(r"@media \(prefers-color-scheme:dark\)\{:root\{(.*?)\}\}", CSS, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", block))


def light_tokens():
    block = re.search(r":root\{(.*?)\n\}", CSS, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{3,6})\b", block))


# ---- Authors belongs to posts, not to static pages --------------------------------------------------------------------------------
def test_the_authors_row_shows_on_posts_only(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": "---\ntitle: About\n---\n<p>x</p>"})
    B.build(site, site / "public")
    assert "<span>Authors</span>" in (site / "public" / "a" / "index.html").read_text(encoding="utf-8")
    about = (site / "public" / "about" / "index.html").read_text(encoding="utf-8")
    assert "Authors" not in about and "Reading time" not in about


def test_a_page_with_a_date_still_has_no_authors_row(tmp_path):
    site = make_site(tmp_path, pages={"talk.html": "---\ntitle: Talk\ndate: 2026-01-01\nauthors: Someone\n---\n<p>x</p>"})
    B.build(site, site / "public")
    page = (site / "public" / "talk" / "index.html").read_text(encoding="utf-8")
    assert "Published" in page and "Authors" not in page


# ---- dark mode ----------------------------------------------------------------------------------------------------------------------
def test_dark_mode_redefines_every_colour_token_it_needs_and_declares_the_scheme():
    dark, light = dark_tokens(), light_tokens()
    assert "color-scheme:dark" in CSS and "color-scheme:light" in CSS
    for name in ("paper", "ink", "muted-2", "rule", "surface", "btn", "btn-ink", "greige", "teal", "sage"):
        assert name in dark and dark[name].lower() != light[name].lower(), name
    assert luminance(dark["paper"]) < 0.05 and luminance(dark["ink"]) > 0.7           # dark paper, light ink


@pytest.mark.parametrize("fg,bg,minimum", [("muted-2", "paper", 4.5), ("ink", "paper", 7), ("btn-ink", "btn", 4.5), ("ink", "surface", 7),
                                           ("muted-2", "surface", 4.5), ("muted-2", "greige", 4.0), ("ink", "greige", 7), ("ink", "teal", 7),
                                           ("ink", "sage", 7)])
def test_dark_text_colour_pairs_are_readable(fg, bg, minimum):
    dark = {**{k: v for k, v in light_tokens().items() if len(v) == 7}, **dark_tokens()}
    assert contrast(dark[fg], dark[bg]) >= minimum


def test_text_on_the_butter_highlight_stays_dark_in_both_schemes():
    assert contrast(light_tokens()["on-butter"].replace("#000", "#000000"), light_tokens()["butter"]) >= 7
    assert "on-butter" not in dark_tokens() and "butter" not in dark_tokens()      # the yellow and its black text are not themed


def test_the_stylesheet_has_no_hard_coded_black_or_white_outside_the_tokens():
    body = CSS.split("/* ---- page skeleton", 1)[1]
    body = re.sub(r"@media print\{.*", "", body)                                   # print wants real black on white
    body = re.sub(r"video\{[^}]*\}", "", body)                                     # video letterbox
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)                               # comments
    body = re.sub(r"\[(?:fill|stroke)=\"[^\"]*\"\]", "", body)                      # the selectors that map figure colours onto tokens
    assert not re.search(r"#000\b|#fff\b|#ffffff\b|#000000\b", body, re.I), re.findall(r"[^;{}]*(?:#000|#fff)[^;}]*", body)[:3]


def test_inline_figures_follow_the_tokens():
    assert '[fill="#fff"]{fill:var(--surface)}' in CSS and '[stroke="#000"]{stroke:var(--ink)}' in CSS and "text.note" in CSS


def test_theme_color_is_set_for_both_schemes(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()})
    B.build(site, site / "public")
    page = (site / "public" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'name="theme-color" content="#F5F4EF" media="\(prefers-color-scheme: light\)"', page)
    assert re.search(rf'name="theme-color" content="{dark_tokens()["paper"]}" media="\(prefers-color-scheme: dark\)"', page)


# ---- tap targets and cards ----------------------------------------------------------------------------------------------------------
def test_nav_links_are_at_least_44px_tall_and_the_project_cards_use_readable_type():
    nav = re.search(r"\nnav a\{([^}]*)\}", CSS).group(1)
    assert "min-height:44px" in nav and "padding:0 8px" in nav
    chip = re.search(r"\n\.chip\{([^}]*)\}", CSS).group(1)
    assert int(re.search(r"font-size:(\d+)px", chip).group(1)) >= 12
    assert "auto-fill" in re.search(r"\n\.chips\{([^}]*)\}", CSS).group(1)         # a lone card is not squeezed into a third of the row


# ---- footer ----------------------------------------------------------------------------------------------------------------------------
def build_home(tmp, **site_over):
    site = make_site(tmp, posts={"a.html": post()}, **site_over)
    B.build(site, site / "public")
    return (site / "public" / "index.html").read_text(encoding="utf-8")


def test_no_page_carries_a_font_credit_line(tmp_path):
    assert "SIL Open Font License" not in build_home(tmp_path)


def test_footer_default_custom_and_off(tmp_path):
    assert "&copy;" in build_home(tmp_path / "a") and 'class="credit"' in build_home(tmp_path / "b")
    assert "<p>Mine</p></footer>" in build_home(tmp_path / "c", footer="<p>Mine</p>")
    off = build_home(tmp_path / "d", footer=False)
    assert "<footer" not in off and "&copy;" not in off


def test_the_home_heading_over_the_post_list_is_configurable_and_escaped(tmp_path):
    assert '<h2 id="posts">Posts</h2>' in build_home(tmp_path / "a")
    assert '<h2 id="posts">Musings &amp; notes</h2>' in build_home(tmp_path / "b", posts_heading="Musings & notes")
