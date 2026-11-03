import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import B, ROOT, contrast, luminance, make_site, post  # noqa: E402

CSS = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")


def dark_tokens():
    block = re.search(r"@media \(prefers-color-scheme:dark\)\{:root\[data-scheme=\"auto\"\]\{(.*?)\}\}", CSS, re.S).group(1)
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


def test_dark_mode_is_off_unless_the_site_opts_in(tmp_path):
    page = build_home(tmp_path)
    assert "data-scheme" not in page and "prefers-color-scheme: dark" not in page
    assert page.count('name="theme-color"') == 1 and 'content="#F5F4EF"' in page


def test_theme_color_is_set_for_both_schemes_when_dark_mode_is_on(tmp_path):
    page = build_home(tmp_path, dark_mode=True)
    assert '<html lang="en" data-scheme="auto">' in page
    assert re.search(r'name="theme-color" content="#F5F4EF" media="\(prefers-color-scheme: light\)"', page)
    assert re.search(rf'name="theme-color" content="{dark_tokens()["paper"]}" media="\(prefers-color-scheme: dark\)"', page)


# ---- tap targets and cards ----------------------------------------------------------------------------------------------------------
def test_nav_links_are_at_least_44px_tall_and_the_project_cards_use_readable_type():
    nav = re.search(r"\nheader\.site nav a\{([^}]*)\}", CSS).group(1)
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


# ---- extra home-page sections ---------------------------------------------------------------------------------------------------------
SECTIONS = [{"id": "crosswords", "heading": "Crosswords"}]


def test_the_home_page_lists_each_section_under_its_own_heading(tmp_path):
    site = make_site(tmp_path, posts={"m.html": post(title="A musing"), "x.html": post(title="A grid", section="crosswords")}, sections=SECTIONS,
                     posts_heading="Musings")
    B.build(site, site / "public")
    home = (site / "public" / "index.html").read_text(encoding="utf-8")
    musings, crosswords = home.split('<h2 id="crosswords">')
    assert '<h2 id="posts">Musings</h2>' in musings and "A musing" in musings and "A grid" not in musings
    assert "Crosswords</h2>" in crosswords and "A grid" in crosswords and "A musing" not in crosswords


def test_an_empty_section_says_so_and_a_draft_section_entry_is_left_out_when_publishing(tmp_path):
    site = make_site(tmp_path, posts={"x.html": post(title="Secret", section="crosswords", draft="true")}, sections=SECTIONS)
    B.build(site, site / "public", publish=True)
    home = (site / "public" / "index.html").read_text(encoding="utf-8")
    assert home.count("Nothing published yet.") == 2 and "Secret" not in home


def test_an_unknown_or_badly_declared_section_is_a_message(tmp_path):
    site = make_site(tmp_path / "a", posts={"x.html": post(section="nope")}, sections=SECTIONS)
    with pytest.raises(B.BuildError, match="section 'nope' is not listed"):
        B.build(site, site / "public")
    for bad in ([{"id": "posts", "heading": "X"}], [{"id": "A b", "heading": "X"}], [{"id": "a"}], SECTIONS + SECTIONS):
        with pytest.raises(B.BuildError, match="section"):
            B.load_site(make_site(tmp_path / f"b{len(str(bad))}", sections=bad))


def test_bare_nav_rules_do_not_exist_so_the_contents_box_is_not_reshaped():
    """A post's "On this page" box is a <nav> too; the header's tap-target styling must stay scoped to header.site."""
    assert not re.search(r"(?m)^nav", CSS)


# ---- one page per section -------------------------------------------------------------------------------------------------------------
def build_sections(tmp, **over):
    site = make_site(tmp, posts={"m.html": post(title="A musing"), "x.html": post(title="A grid", section="crosswords")}, sections=SECTIONS,
                     pages={"about.html": "---\ntitle: About\n---\n<p>x</p>"},
                     posts_heading="Musings", posts_slug="musings", **over)
    B.build(site, site / "public")
    return site / "public"


def test_each_section_has_a_page_showing_only_its_own_entries(tmp_path):
    out = build_sections(tmp_path)
    musings = (out / "musings" / "index.html").read_text(encoding="utf-8")
    crosswords = (out / "crosswords" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Musings</h1>" in musings and "A musing" in musings and "A grid" not in musings
    assert "<h1>Crosswords</h1>" in crosswords and "A grid" in crosswords and "A musing" not in crosswords
    assert 'href="../m/index.html"' in musings and 'href="../x/index.html"' in crosswords          # links work from the section page
    assert B.check_links(out) == []


def test_the_home_page_stays_an_overview_of_every_section(tmp_path):
    home = (build_sections(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "A musing" in home and "A grid" in home


def test_the_nav_marks_the_section_page_you_are_on(tmp_path):
    out = build_sections(tmp_path, nav=[{"label": "Musings", "href": "musings/index.html"}, {"label": "Crosswords", "href": "crosswords/index.html"}])
    page = (out / "crosswords" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<a href="../crosswords/index.html" aria-current="page">Crosswords</a>', page)
    assert 'aria-current="page">Musings' not in page


def test_section_pages_are_in_the_sitemap_and_default_to_posts(tmp_path):
    out = build_sections(tmp_path)
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "/musings/index.html" in sm and "/crosswords/index.html" in sm
    site = make_site(tmp_path / "d", posts={"m.html": post()})
    B.build(site, site / "public")
    assert (site / "public" / "posts" / "index.html").exists()


def test_a_post_cannot_take_a_section_address(tmp_path):
    site = make_site(tmp_path, posts={"crosswords.html": post()}, sections=SECTIONS)
    with pytest.raises(B.BuildError, match="is a section page"):
        B.build(site, site / "public")


# ---- links that are not filled in yet ------------------------------------------------------------------------------------------------
def post_page(tmp, links):
    site = make_site(tmp, posts={"a.html": post(links=links)})
    B.build(site, site / "public")
    return (site / "public" / "a" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("links", ["Code | #", "Code |", "Code |  ;", "Code | #; Paper | #"])
def test_a_link_that_is_not_filled_in_is_hidden_and_so_is_an_empty_button_row(tmp_path, links):
    page = post_page(tmp_path, links)
    assert ">Code<" not in page and ">Paper<" not in page and 'class="btns"' not in page


def test_only_the_filled_in_links_are_shown(tmp_path):
    page = post_page(tmp_path, "Code | #; Paper | https://example.org/p")
    assert ">Code<" not in page and '<a class="btn" href="https://example.org/p">Paper</a>' in page


@pytest.mark.parametrize("links", ["Code", "| https://example.org", "Code https://example.org"])
def test_a_malformed_link_is_still_a_message(links):
    with pytest.raises(B.BuildError, match="links must look like"):
        B.parse_links(links, "f")
