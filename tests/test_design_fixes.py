import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import B, ROOT, contrast, luminance, make_site, post  # noqa: E402

CSS = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")


def dark_tokens():
    block = re.search(r"@media\s+screen\s+and\s+\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\[data-scheme=[\"']auto[\"']\]\s*\{(.*?)\}\s*\}", CSS, re.S)
    assert block, "the dark palette must sit in @media screen and (prefers-color-scheme:dark){:root[data-scheme=auto]{...}}"
    return dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})", block.group(1)))


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


def test_every_nav_rule_is_scoped_to_the_site_header_so_the_contents_box_is_not_reshaped():
    """A post's "On this page" box is a <nav> too; the header's tap-target styling must stay scoped to header.site."""
    selectors = re.findall(r"(?m)^([^{}/@]*\bnav\b[^{]*)\{", CSS)
    assert selectors and all(sel.strip().startswith("header.site") for sel in selectors), selectors
    assert not re.search(r"(?m)^\s*nav\b", CSS)


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


# ---- no tags -----------------------------------------------------------------------------------------------------------------------------
def test_tags_are_gone_a_tags_line_in_front_matter_is_ignored_and_no_tag_pills_appear(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(tags="one, two")})
    B.build(site, site / "public")
    page = (site / "public" / "a" / "index.html").read_text(encoding="utf-8")
    assert "Tags" not in page and ">one<" not in page and 'class="pill"' not in page


# ---- author pages -------------------------------------------------------------------------------------------------------------------------
ABOUT = "---\ntitle: About\n---\n<p>x</p>"


def authors_site(tmp, posts, **over):
    site = make_site(tmp, posts=posts, author_pages=True, pages={"about.html": ABOUT}, **over)
    return site


def build_out(site, **kw):
    B.build(site, site / "public", **kw)
    return site / "public"


def test_authors_are_plain_text_and_no_author_pages_exist_unless_the_site_opts_in(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(authors="A. Writer, B. Coauthor")})
    out = build_out(site)
    page = (out / "a" / "index.html").read_text(encoding="utf-8")
    assert "<span>A. Writer, B. Coauthor</span>" in page and "authors/" not in page and not (out / "authors").exists()


def test_each_author_links_to_a_page_listing_only_their_posts_and_there_is_an_index(tmp_path):
    site = authors_site(tmp_path, {"one.html": post(title="One", authors="A. Writer, B. Coauthor"), "two.html": post(title="Two", date="2026-03-01", authors="B. Coauthor"),
                                   "three.html": post(title="Three", date="2026-01-01", authors="C. Solo")})
    out = build_out(site)
    page = (out / "one" / "index.html").read_text(encoding="utf-8")
    assert '<a href="../authors/a-writer/index.html">A. Writer</a>, <a href="../authors/b-coauthor/index.html">B. Coauthor</a>' in page
    coauthor = (out / "authors" / "b-coauthor" / "index.html").read_text(encoding="utf-8")
    assert "<h1>B. Coauthor</h1>" in coauthor and "One" in coauthor and "Two" in coauthor and "Three" not in coauthor
    assert coauthor.index("Two") < coauthor.index("One")                                       # newest first
    assert 'href="../../two/index.html"' in coauthor                                           # links work from two levels down
    index = (out / "authors" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Authors</h1>" in index and "2 posts" in index and "1 post<" in index and 'href="b-coauthor/index.html"' in index
    assert B.check_links(out) == []


def test_the_site_author_is_the_default_author_and_gets_a_page(tmp_path):
    out = build_out(authors_site(tmp_path, {"a.html": post()}))
    assert (out / "authors" / "a-writer" / "index.html").exists()                              # the helper site's author is "A. Writer"


def test_authors_names_are_escaped_and_accents_fold_into_the_address(tmp_path):
    out = build_out(authors_site(tmp_path, {"a.html": post(authors="Zoë <b>Q</b> Writer")}))
    page = (out / "a" / "index.html").read_text(encoding="utf-8")
    assert "<b>Q</b>" not in page and "Zoë &lt;b&gt;Q&lt;/b&gt; Writer" in page
    assert (out / "authors" / "zoe-b-q-b-writer" / "index.html").exists()


def test_publishing_leaves_out_authors_who_only_have_drafts(tmp_path):
    site = authors_site(tmp_path, {"a.html": post(), "d.html": post(title="D", authors="Ghost Writer", draft="true")})
    out = build_out(site, publish=True)
    assert not (out / "authors" / "ghost-writer").exists() and "Ghost" not in (out / "authors" / "index.html").read_text(encoding="utf-8")
    assert B.check_links(out) == []
    assert "authors/ghost-writer" not in (out / "sitemap.xml").read_text(encoding="utf-8") and "authors/a-writer/index.html" in (out / "sitemap.xml").read_text(encoding="utf-8")


def test_author_pages_have_no_authors_row_on_static_pages_and_none_when_there_are_no_posts(tmp_path):
    site = make_site(tmp_path, pages={"about.html": "---\ntitle: About\n---\n<p>x</p>"}, author_pages=True)
    out = build_out(site)
    assert "Nothing published yet." in (out / "authors" / "index.html").read_text(encoding="utf-8")
    assert "Authors" not in (out / "about" / "index.html").read_text(encoding="utf-8").split("<main")[1]


@pytest.mark.parametrize("posts,match", [
    ({"a.html": post(authors="Jo Smith"), "b.html": post(authors="jo  smith")}, "would both live at authors/jo-smith"),
    ({"a.html": post(authors="Zoë"), "b.html": post(authors="Zoe")}, "would both live at authors/zoe"),
    ({"a.html": post(authors="张伟")}, "has no letters or digits"),
    ({"authors.html": post()}, "'authors' is used by the author pages"),
])
def test_author_address_problems_are_messages(tmp_path, posts, match):
    site = authors_site(tmp_path, posts)
    with pytest.raises(B.BuildError, match=match):
        B.build(site, site / "public")


def test_author_pages_must_be_a_boolean_and_cannot_clash_with_a_section(tmp_path):
    with pytest.raises(B.BuildError, match="'author_pages' must be true or false"):
        B.load_site(make_site(tmp_path / "a", author_pages="yes"))
    site = make_site(tmp_path / "b", posts={"a.html": post()}, author_pages=True, sections=[{"id": "authors", "heading": "Authors"}])
    with pytest.raises(B.BuildError, match="cannot use the address 'authors'"):
        B.build(site, site / "public")


# ---- review round: CSS ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("attr,literal,token", [("fill", "#fff", "surface"), ("fill", "#000", "ink"), ("stroke", "#000", "ink"), ("fill", "#EEEDE8", "tab"),
                                                ("fill", "rgba(44,40,26,.09)", "shadow-soft"), ("stroke", "#B4B3AF", "rule"), ("fill", "#F5F4EF", "paper")])
def test_every_literal_figure_colour_is_mapped_onto_its_token(attr, literal, token):
    pattern = rf'\.paper svg \[{attr}="{re.escape(literal)}"\]\s*\{{\s*{attr}\s*:\s*var\(--{token}\)'
    assert re.search(pattern, CSS), (attr, literal, token)


def test_note_text_in_figures_stays_dark_on_butter():
    assert re.search(r"\.paper svg text\.note\s*\{\s*fill\s*:\s*var\(--on-butter\)", CSS)


def test_every_rule_with_a_butter_background_also_sets_the_dark_text_colour():
    for body in re.findall(r"\{([^{}]*)\}", CSS):
        if re.search(r"background\s*:\s*var\(--butter\)", body):
            assert re.search(r"color\s*:\s*var\(--on-butter\)", body), body


def test_links_code_and_focus_rings_inside_the_butter_highlight_use_the_dark_text_colour():
    assert re.search(r"\.callout a[^{]*\{[^}]*color:var\(--on-butter\)", CSS)
    assert re.search(r"\.callout code[^{]*\{[^}]*color:var\(--on-butter\)", CSS)
    assert re.search(r"\.callout :focus-visible[^{]*\{[^}]*outline-color:var\(--on-butter\)", CSS)


def test_no_colour_keywords_outside_the_tokens():
    body = re.sub(r"/\*.*?\*/", "", CSS.split(".skip{", 1)[1], flags=re.S)
    body = re.sub(r"@media print\{.*", "", body)
    assert not re.search(r"\b(?:black|white)\b", body, re.I)


def test_only_links_lift_on_hover_not_every_chip_and_wide_grids_cannot_force_overflow():
    assert "a.chip:hover" in CSS and not re.search(r"(?m)^\.chip:hover", CSS)
    assert "repeat(3,minmax(0,1fr))" in CSS and "overflow-wrap:anywhere" in CSS
    assert not re.search(r"grid-template-columns:\s*1fr\s*[}\]]", CSS) and "grid-template-columns:repeat(3,1fr)" not in CSS


def test_the_dark_palette_applies_to_screens_not_to_print():
    assert re.search(r"@media\s+screen\s+and\s+\(prefers-color-scheme:\s*dark\)", CSS)


# ---- review round: config types ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("key,value,match", [
    ("sections", None, "'sections' must be a list"), ("nav", None, "'nav' must be a list"), ("posts_slug", 5, "'posts_slug' must be text"),
    ("posts_slug", None, "'posts_slug' must be text"), ("posts_heading", None, "'posts_heading' must be text"), ("posts_heading", 5, "'posts_heading' must be text"),
    ("title", 5, "'title' must be text"), ("description", None, "'description' must be text"), ("lang", None, "'lang' must be text"),
    ("intro", 5, "'intro' must be text"), ("url", 5, "'url' must be text"), ("footer", True, "'footer' must be text"),
    ("footer", ["a"], "'footer' must be text"), ("dark_mode", "false", "'dark_mode' must be true or false"), ("dark_mode", 1, "'dark_mode' must be true or false"),
])
def test_wrong_typed_site_json_values_are_messages_not_tracebacks(tmp_path, key, value, match):
    with pytest.raises(B.BuildError, match=match):
        B.load_site(make_site(tmp_path, **{key: value}))


def test_section_addresses_and_posts_slug_reject_reserved_names_with_the_right_message(tmp_path):
    with pytest.raises(B.BuildError, match="must look like"):
        B.load_site(make_site(tmp_path / "p", sections=[{"id": "posts", "heading": "X"}], posts_slug="musings"))
    for i, slug in enumerate(("theme", "images", "feed", "sitemap", "index", "content")):
        with pytest.raises(B.BuildError, match="not a usable section address"):
            B.load_site(make_site(tmp_path / f"s{i}", sections=[{"id": slug, "heading": "X"}]))
        with pytest.raises(B.BuildError, match="not a usable section address"):
            B.load_site(make_site(tmp_path / f"q{i}", posts_slug=slug))
    with pytest.raises(B.BuildError, match="must be unique"):
        B.load_site(make_site(tmp_path / "d", sections=SECTIONS + SECTIONS))


# ---- review round: sections and drafts -----------------------------------------------------------------------------------------------------
def test_a_section_page_has_its_own_title_canonical_feed_link_stylesheet_and_an_escaped_heading(tmp_path):
    site = make_site(tmp_path, posts={"x.html": post(section="q")}, sections=[{"id": "q", "heading": "A & B"}], pages={"about.html": ABOUT})
    out = build_out(site)
    page = (out / "q" / "index.html").read_text(encoding="utf-8")
    assert "<h1>A &amp; B</h1>" in page and "<title>A &amp; B | Test Blog</title>" in page
    assert '<link rel="canonical" href="https://blog.example/q/index.html">' in page
    assert 'rel="alternate" type="application/atom+xml"' in page and 'href="../theme/style.css"' in page


def test_a_draft_section_entry_is_hidden_on_its_section_page_when_publishing_and_badged_otherwise(tmp_path):
    site = make_site(tmp_path, posts={"d.html": post(title="Secret", section="crosswords", draft="true")}, sections=SECTIONS, pages={"about.html": ABOUT})
    assert "Secret" not in (build_out(site, publish=True) / "crosswords" / "index.html").read_text(encoding="utf-8")
    page = (build_out(site) / "crosswords" / "index.html").read_text(encoding="utf-8")
    assert "Secret" in page and "draft</span>" in page


def test_an_address_clash_or_unknown_section_in_a_draft_is_reported_even_when_publishing(tmp_path):
    site = make_site(tmp_path / "a", posts={"x.html": post()}, sections=SECTIONS)
    (site / "content" / "drafts").mkdir()
    (site / "content" / "drafts" / "crosswords.html").write_text(post(), encoding="utf-8")
    with pytest.raises(B.BuildError, match="is a section page"):
        B.build(site, site / "public", publish=True)
    site = make_site(tmp_path / "b", posts={"x.html": post()}, sections=SECTIONS)
    (site / "content" / "drafts").mkdir()
    (site / "content" / "drafts" / "d.html").write_text(post(section="zz"), encoding="utf-8")
    with pytest.raises(B.BuildError, match="section 'zz' is not listed"):
        B.build(site, site / "public", publish=True)


def test_a_section_called_content_and_a_heading_called_content_cannot_make_duplicate_ids(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post(body="<h2>Content</h2><p>x</p>")}, pages={"about.html": ABOUT})
    page = (build_out(site) / "a" / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', page)
    assert len(ids) == len(set(ids)) and 'id="content-2"' in page


def test_two_sections_keep_the_order_of_site_json_on_the_home_page_and_in_the_sitemap(tmp_path):
    secs = [{"id": "zeta", "heading": "Zeta"}, {"id": "alpha", "heading": "Alpha"}]
    site = make_site(tmp_path, posts={"a.html": post()}, sections=secs, pages={"about.html": ABOUT})
    out = build_out(site)
    home = (out / "index.html").read_text(encoding="utf-8")
    assert home.index('id="zeta"') < home.index('id="alpha"')
    sm = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert sm.index("/zeta/") < sm.index("/alpha/") and "\\" not in sm and "\\" not in home


def test_nav_marks_the_current_page_for_dot_slash_and_query_forms(tmp_path):
    for i, href in enumerate(("./crosswords/index.html", "crosswords/index.html?x=1")):
        out = build_out(make_site(tmp_path / f"n{i}", posts={"a.html": post()}, sections=SECTIONS, pages={"about.html": ABOUT},
                                  nav=[{"label": "Crosswords", "href": href}]))
        assert 'aria-current="page">Crosswords' in (out / "crosswords" / "index.html").read_text(encoding="utf-8")


def test_a_site_without_its_own_favicon_still_gets_one_and_passes_the_link_check(tmp_path):
    site = make_site(tmp_path, posts={"a.html": post()}, pages={"about.html": ABOUT})
    (site / "content" / "images" / "favicon.svg").unlink()
    out = build_out(site)
    assert (out / "images" / "favicon.svg").exists() and B.check_links(out) == []


# ---- review round: the link checker ------------------------------------------------------------------------------------------------------------
def test_check_links_notices_a_wrong_case_and_understands_percent_escapes_and_srcset_and_root_relative_links(tmp_path):
    out = tmp_path / "out"
    (out / "other").mkdir(parents=True)
    (out / "other" / "index.html").write_text("<p>x</p>", encoding="utf-8")
    (out / "a b.png").write_bytes(b"x")
    page = ('<a href="other/index.html">ok</a><a href="Other/index.html">wrong case</a><img src="a%20b.png">'
            '<img src="a b.png" srcset="a%20b.png 1x, missing.png 2x"><a href="/other/index.html">root</a><a href="/nope/index.html">root missing</a>')
    (out / "index.html").write_text(page, encoding="utf-8")
    problems = " | ".join(B.check_links(out))
    assert "'Other/index.html'" in problems and "'missing.png'" in problems and "'/nope/index.html'" in problems
    assert "a%20b.png" not in problems and "'other/index.html'" not in problems and "'/other/index.html'" not in problems


def test_the_default_footer_names_the_author_and_the_year_and_an_empty_footer_is_the_default(tmp_path):
    import datetime
    for i, footer in enumerate(("", None)):
        over = {} if footer is None else {"footer": footer}
        home = build_home(tmp_path / f"f{i}", **over)
        assert f"&copy; {datetime.date.today().year} A. Writer</p></footer>" in home


# ---- author pages tell sections apart ------------------------------------------------------------------------------------------------------------
def sectioned_authors(tmp, **over):
    posts = {"m1.html": post(title="Musing One", date="2026-03-01", authors="A. Writer, B. Coauthor"),
             "m2.html": post(title="Musing Two", date="2026-01-01", authors="A. Writer"),
             "x1.html": post(title="Grid One", date="2026-02-01", section="crosswords", authors="A. Writer"),
             "x2.html": post(title="Grid Two", date="2026-04-01", section="crosswords", authors="B. Coauthor")}
    return build_out(make_site(tmp, posts=posts, author_pages=True, posts_heading="Musings", sections=SECTIONS, pages={"about.html": ABOUT}, **over))


def test_an_author_page_groups_entries_under_a_heading_per_section(tmp_path):
    page = (sectioned_authors(tmp_path) / "authors" / "a-writer" / "index.html").read_text(encoding="utf-8")
    assert page.index('<h2 id="posts">Musings</h2>') < page.index("Musing One") < page.index("Musing Two") < page.index('<h2 id="crosswords">Crosswords</h2>') < page.index("Grid One")
    assert "Grid Two" not in page and 'href="../../x1/index.html"' in page


def test_a_group_with_no_entries_for_that_author_is_left_out(tmp_path):
    out = build_out(make_site(tmp_path, posts={"m.html": post(title="Only Musing"), "x.html": post(title="Grid", section="crosswords", authors="Other Setter")},
                              author_pages=True, posts_heading="Musings", sections=SECTIONS, pages={"about.html": ABOUT}))
    page = (out / "authors" / "a-writer" / "index.html").read_text(encoding="utf-8")
    assert "Musings</h2>" in page and "Crosswords</h2>" not in page
    other = (out / "authors" / "other-setter" / "index.html").read_text(encoding="utf-8")
    assert "Crosswords</h2>" in other and "Musings</h2>" not in other


def test_the_authors_index_shows_a_breakdown_by_section_and_stays_plain_without_sections(tmp_path):
    index = (sectioned_authors(tmp_path / "s") / "authors" / "index.html").read_text(encoding="utf-8")
    assert "<p>Musings 2 · Crosswords 1</p>" in index and "<p>Musings 1 · Crosswords 1</p>" in index and "3 posts" in index
    plain = build_out(make_site(tmp_path / "p", posts={"a.html": post()}, author_pages=True, pages={"about.html": ABOUT}))
    assert "<h2" not in (plain / "authors" / "a-writer" / "index.html").read_text(encoding="utf-8").split("<main")[1]
    assert "·" not in (plain / "authors" / "index.html").read_text(encoding="utf-8")


def test_section_headings_on_author_pages_are_escaped_and_follow_site_json_order(tmp_path):
    secs = [{"id": "zeta", "heading": "Z & Co"}, {"id": "alpha", "heading": "Alpha"}]
    out = build_out(make_site(tmp_path, posts={"a.html": post(section="alpha", title="A1"), "z.html": post(section="zeta", title="Z1")}, author_pages=True,
                              sections=secs, posts_heading="Notes", pages={"about.html": ABOUT}))
    page = (out / "authors" / "a-writer" / "index.html").read_text(encoding="utf-8")
    assert page.index("Z &amp; Co") < page.index(">Alpha<") and "Z & Co" not in page
    assert B.check_links(out) == []
