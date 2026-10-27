import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402
from test_build import make_site, post  # noqa: E402


@pytest.fixture
def site(tmp_path):
    return make_site(tmp_path)


def expand(site, text, page_root="../"):
    return B.expand_shortcodes(text, B.Ctx(site, page_root, "test.html"))


def add_snippet(site, name, html):
    d = site / "content" / "snippets"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.html").write_text(html, encoding="utf-8")


# ---- calling a piece -------------------------------------------------------------------------------------------------------
def test_an_inline_call_fills_plain_and_named_arguments(site):
    assert expand(site, '{{pill "new" color=butter}}') == '<span class="pill butter">new</span>'
    assert expand(site, "{{pill plain}}") == '<span class="pill ">plain</span>'


def test_a_block_call_wraps_html_and_optional_parts_can_be_left_out(site):
    out = expand(site, '{{#callout title="Heads up"}}<p>Body</p>{{/callout}}')
    assert out == '<div class="callout"><b>Heads up</b> <p>Body</p></div>'
    assert "<b></b>" in expand(site, "{{#callout}}x{{/callout}}")             # empty; the stylesheet hides an empty <b>


def test_arguments_are_html_escaped_but_the_body_is_not(site):
    out = expand(site, '{{#callout title="<script>alert(1)</script> & \\"q\\""}}<em>kept</em>{{/callout}}')
    assert "<script>" not in out and "&lt;script&gt;" in out and "&amp;" in out and "<em>kept</em>" in out
    assert 'data-tip="a &lt;b&gt; &quot;c&quot;"' in expand(site, '{{term word tip="a <b> \\"c\\""}}')
    assert 'data-tip="use &lt;code&gt;x&lt;/code&gt;"' in expand(site, '{{term word tip="use <code>x</code>"}}')       # markup in an argument is text


def test_quoted_arguments_keep_their_spaces_and_apostrophes(site):
    assert "it&#x27;s two words" in expand(site, '{{pill "it\'s two words"}}')


def test_blocks_nest_and_the_same_name_can_nest_in_itself(site):
    out = expand(site, "{{#card}}outer {{#card variant=strong}}inner{{/card}} end{{/card}}")
    assert out == '<div class="card ">outer <div class="card strong">inner</div> end</div>'
    out = expand(site, '{{#facts}}{{fact value="1" label="a"}}{{fact value="2"}}{{/facts}}')
    assert out.count('class="fact"') == 2 and out.startswith('<div class="facts">') and "<b>2</b></div>" in out


def test_the_page_root_is_available_so_images_work_from_any_depth(site):
    assert 'src="../images/p.png"' in expand(site, '{{image src="images/p.png" alt="A picture"}}', "../")
    assert 'src="images/p.png"' in expand(site, '{{image src="images/p.png" alt="A picture"}}', "")
    assert 'aria-label="A clip"' in expand(site, '{{video src="images/v.mp4" label="A clip"}}')


def test_pieces_can_be_added_and_replaced_by_the_author(site):
    add_snippet(site, "warn", '<p class="warn">{{1}}: {{msg|careful}}</p>')
    assert expand(site, "{{warn Note}}") == '<p class="warn">Note: careful</p>'
    assert expand(site, '{{warn Note msg="really"}}') == '<p class="warn">Note: really</p>'
    add_snippet(site, "pill", '<mark>{{1}}</mark>')                                  # a file in content/snippets wins over the built-in
    assert expand(site, "{{pill x}}") == "<mark>x</mark>"


# ---- text that must not be touched ------------------------------------------------------------------------------------------------
def test_code_and_scripts_are_left_alone_even_inside_a_wrapping_call(site):
    src = '<pre><code>{{pill "x"}}</code></pre><script>var a = "{{b}}";</script><style>/* {{c}} */</style><code>{{#d}}</code>'
    assert expand(site, src) == src
    out = expand(site, "{{#card}}<pre>{{pill}}</pre> and {{pill ok}}{{/card}}")
    assert "<pre>{{pill}}</pre>" in out and '<span class="pill ">ok</span>' in out


def test_a_backslash_writes_the_braces_literally(site):
    assert expand(site, r"write \{{pill}} to call it") == "write {{pill}} to call it"


def test_values_that_look_like_calls_are_not_expanded_a_second_time(site):
    assert expand(site, '{{pill "{{x"}}') == '<span class="pill ">{{x</span>'


def test_a_snippet_cannot_be_exploited_through_braces_in_the_body(site):
    add_snippet(site, "box", "<div>{{{body}}}</div>")
    assert expand(site, r"{{#box}}\{{pill}}{{/box}}") == "<div>{{pill}}</div>"


# ---- mistakes: every one names the file and says what to do ------------------------------------------------------------------------
@pytest.mark.parametrize("text,msg", [
    ("{{nothing}}", "no snippet called 'nothing' .*available: .*callout"),
    ("{{title}}", "no snippet called 'title'"),                                          # a layout placeholder is not a call
    ('{{pill x colour=teal}}', "no parameter 'colour'; it takes: color, 1"),
    ("{{pill a b}}", "takes 1 plain argument"),
    ("{{image src=x}}", "needs 'alt'"),
    ("{{fact label=x}}", "needs 'value'"),
    ("{{#pill x}}y{{/pill}}", "does not wrap content"),
    ("{{#card}}never closed", "never closed with {{/card}}"),
    ("{{/card}}", "closes nothing"),
    ("{{#card}}{{#callout}}x{{/card}}{{/callout}}", r"where \{\{/callout\}\} was expected"),
    ('{{pill "unterminated}}', "quote values that contain spaces"),
    ("{{svg ../site.json}}", "needs the name of an .svg file"),
    ("{{svg missing.svg}}", "needs the name of an .svg file"),
])
def test_mistakes_are_explained_with_the_file_name(site, text, msg):
    with pytest.raises(B.BuildError, match=msg) as e:
        expand(site, text)
    assert "test.html" in str(e.value)


# ---- inline SVG ----------------------------------------------------------------------------------------------------------------------
def test_svg_files_are_inlined_without_their_xml_prolog(site):
    (site / "content" / "images" / "d.svg").write_text('<?xml version="1.0"?>\n<!DOCTYPE svg>\n<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>\n',
                                                       encoding="utf-8")
    assert expand(site, "{{svg d.svg}}") == '<svg viewBox="0 0 1 1"><path d="M0 0"/></svg>'
    assert expand(site, "{{svg src=d.svg}}") == expand(site, "{{svg d.svg}}")


def test_svg_refuses_files_that_are_not_svg_or_are_outside_the_images_folder(site):
    (site / "content" / "images" / "bad.svg").write_text("<html></html>", encoding="utf-8")
    (site / "secret.svg").write_text("<svg/>", encoding="utf-8")
    for src in ("bad.svg", "../../secret.svg", "/etc/passwd", ""):
        with pytest.raises(B.BuildError):
            expand(site, f'{{{{svg "{src}"}}}}')


# ---- in a real build -------------------------------------------------------------------------------------------------------------------
def test_shortcodes_work_in_posts_and_in_the_site_intro(tmp_path):
    make_site(tmp_path, posts={"a.html": post(body='{{pill hello color=teal}}{{#callout}}x{{/callout}}')}, intro='{{pill "from intro"}}')
    B.build(tmp_path, tmp_path / "out")
    assert 'class="pill teal">hello' in (tmp_path / "out" / "a" / "index.html").read_text(encoding="utf-8")
    assert 'class="pill ">from intro' in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")


def test_a_draft_piece_is_removed_by_publish_but_shown_otherwise(tmp_path):
    make_site(tmp_path, posts={"a.html": post(body='<p>keep</p>{{#draft}}SECRET-NOTE{{/draft}}')})
    B.build(tmp_path, tmp_path / "dev")
    B.build(tmp_path, tmp_path / "pub", publish=True)
    assert "SECRET-NOTE" in (tmp_path / "dev" / "a" / "index.html").read_text(encoding="utf-8")
    pub = (tmp_path / "pub" / "a" / "index.html").read_text(encoding="utf-8")
    assert "SECRET-NOTE" not in pub and "<p>keep</p>" in pub


def test_a_mistake_in_a_post_stops_the_build_with_that_posts_file_name(tmp_path):
    make_site(tmp_path, posts={"broken.html": post(body="{{#card}}oops")})
    with pytest.raises(B.BuildError, match="broken.html.*never closed"):
        B.build(tmp_path, tmp_path / "out")


def test_the_components_folder_is_not_published_but_the_snippets_folder_never_is_either(tmp_path):
    make_site(tmp_path, posts={"a.html": post(body="{{pill x}}")})
    add_snippet(tmp_path, "extra", "<p>x</p>")
    B.build(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out" / "theme" / "components").exists() and not (tmp_path / "out" / "snippets").exists()


# ---- the shipped pieces ---------------------------------------------------------------------------------------------------------------
SAMPLE_CALLS = {
    "callout": "{{#callout title=T}}b{{/callout}}", "card": "{{#card variant=strong}}b{{/card}}", "facts": "{{#facts}}b{{/facts}}",
    "fact": "{{fact value=1 label=l}}", "chips": "{{#chips}}b{{/chips}}", "chip": "{{chip href=h title=t text=x}}", "pill": "{{pill p color=teal}}",
    "button": "{{button B href=h}}", "wide": "{{#wide}}b{{/wide}}", "full": "{{#full}}b{{/full}}", "figure": "{{#figure caption=c}}b{{/figure}}",
    "image": "{{image src=s alt=a caption=c width=wide}}", "video": "{{video src=s label=l caption=c}}", "term": "{{term w tip=t title=T}}",
    "quote": "{{#quote cite=c}}b{{/quote}}", "appendix": "{{#appendix title=T}}b{{/appendix}}", "draft": "{{#draft title=T}}b{{/draft}}",
}


def test_every_shipped_piece_has_a_sample_and_builds_without_leftover_braces(site):
    shipped = {p.stem for p in (ROOT / "theme" / "components").glob("*.html")}
    assert shipped == set(SAMPLE_CALLS), "add a sample call here for every new built-in piece"
    for name, call in SAMPLE_CALLS.items():
        out = expand(site, call)
        assert "{{" not in out and "}}" not in out and out.startswith("<"), (name, out)


def test_shipped_pieces_produce_balanced_html(site):
    from html.parser import HTMLParser

    class Balance(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = []

        def handle_starttag(self, tag, attrs):
            if tag not in B.VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack.pop() == tag, tag
    for name, call in SAMPLE_CALLS.items():
        p = Balance()
        p.feed(expand(site, call))
        assert not p.stack, (name, p.stack)


def test_the_shipped_site_uses_the_pieces_and_every_snippet_name_in_the_docs_exists(tmp_path):
    shipped = {p.stem for p in (ROOT / "theme" / "components").glob("*.html")} | {"svg"}
    text = (ROOT / "content" / "posts" / "components.html").read_text(encoding="utf-8")
    table = re.search(r"<tbody>.*?</tbody>", text[text.index("Reusable pieces"):], re.S).group(0)
    named = {n for cell in re.findall(r"<th>(.*?)</th>", table) for n in re.findall(r"<code>(\w+)</code>", cell)}
    assert named <= shipped, named - shipped
    assert named == shipped, (named ^ shipped)
