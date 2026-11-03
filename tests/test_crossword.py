import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import B, ROOT, make_site, post  # noqa: E402

ABOUT = "---\ntitle: About\n---\n<p>x</p>"
DEMO = ROOT / "content" / "posts" / "components" / "mini.ipuz"


def ipuz(solution, across, down, **over):
    """A small ipuz dict: solution rows ('#' is a block), clues as {number: text}."""
    h, w = len(solution), len(solution[0])
    doc = {"version": "http://ipuz.org/v2", "kind": ["http://ipuz.org/crossword#1"], "dimensions": {"width": w, "height": h},
           "puzzle": [[0 if ch != "#" else "#" for ch in row] for row in solution], "solution": [[ch for ch in row] for row in solution],
           "clues": {"Across": [[n, t] for n, t in across.items()], "Down": [[n, t] for n, t in down.items()]}}
    doc.update(over)
    return doc


RING = ipuz(["ABC", "D#E", "FGH"], {1: "Top", 3: "Bottom"}, {1: "Left", 2: "Right"}, title="Ring", author="A. Setter")


def write(tmp, doc, name="p.ipuz"):
    path = tmp / name
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    return path


# ---- reading and numbering ------------------------------------------------------------------------------------------------------------
def test_numbering_follows_the_standard_rules_with_blocks():
    numbers, across, down = B.number_grid(["ABC", "D#E", "FGH"])
    assert numbers == {(0, 0): 1, (0, 2): 2, (2, 0): 3}
    assert [(n, cells) for n, cells in across] == [(1, [(0, 0), (0, 1), (0, 2)]), (3, [(2, 0), (2, 1), (2, 2)])]
    assert [(n, cells) for n, cells in down] == [(1, [(0, 0), (1, 0), (2, 0)]), (2, [(0, 2), (1, 2), (2, 2)])]


def test_the_demo_puzzle_reads_and_has_a_stable_id():
    puzzle = B.read_ipuz(DEMO, "x")
    assert puzzle["grid"] == ["HEART", "EMBER", "ABUSE", "RESIN", "TREND"] and (puzzle["w"], puzzle["h"]) == (5, 5)
    assert [n for n, _ in puzzle["across"]] == [1, 6, 7, 8, 9] and [n for n, _ in puzzle["down"]] == [1, 2, 3, 4, 5]
    assert puzzle["title"] == "Five by five" and puzzle["author"] == "Demo"
    assert puzzle["id"] == B.read_ipuz(DEMO, "y")["id"] and len(puzzle["id"]) == 12


def test_the_id_follows_the_grid_not_the_clues(tmp_path):
    a = B.read_ipuz(write(tmp_path, RING), "x")
    b = B.read_ipuz(write(tmp_path, ipuz(["ABC", "D#E", "FGH"], {1: "Other", 3: "Words"}, {1: "Here", 2: "Too"}), "q.ipuz"), "x")
    c = B.read_ipuz(write(tmp_path, ipuz(["ABC", "D#E", "FGZ"], {1: "Top", 3: "Bottom"}, {1: "Left", 2: "Right"}), "r.ipuz"), "x")
    assert a["id"] == b["id"] != c["id"]


def test_blocks_can_be_null_or_a_custom_block_marker_and_circles_and_dict_cells_are_read(tmp_path):
    doc = ipuz(["ABC", "D#E", "FGH"], {1: "Top", 3: "Bottom"}, {1: "Left", 2: "Right"})
    doc["solution"][1][1] = None
    doc["puzzle"][1][1] = None
    doc["puzzle"][0][0] = {"cell": 1, "style": {"shapebg": "circle"}}
    doc["solution"][2][2] = {"value": "h"}
    puzzle = B.read_ipuz(write(tmp_path, doc), "x")
    assert puzzle["grid"] == ["ABC", "D#E", "FGH"] and puzzle["circles"] == [[0, 0]]
    custom = ipuz(["AB", "CD"], {1: "x", 3: "y"}, {1: "z", 2: "w"}, block="X")
    custom["solution"] = [["A", "B"], ["C", "D"]]
    assert B.read_ipuz(write(tmp_path, custom, "c.ipuz"), "x")["grid"] == ["AB", "CD"]


def test_a_jsonp_wrapper_and_a_bom_are_tolerated(tmp_path):
    wrapped = "﻿ipuz(" + json.dumps(RING) + ");"
    assert B.read_ipuz(write(tmp_path, wrapped), "x")["title"] == "Ring"


@pytest.mark.parametrize("mutate,match", [
    (lambda d: d.update(kind=["http://ipuz.org/sudoku#1"]), "is not an ipuz crossword"),
    (lambda d: d.update(dimensions={"width": 4, "height": 3}), "must be 3 rows of 4 squares|must be 3 rows"),
    (lambda d: d.update(dimensions={"width": 99, "height": 99}), "between 2 and"),
    (lambda d: d.update(dimensions={"width": "x"}), "must give a width and a height"),
    (lambda d: d["solution"][0].__setitem__(0, "AB"), "no rebus"),
    (lambda d: d["solution"][0].__setitem__(0, ""), "no solution letter"),
    (lambda d: d["clues"]["Across"].pop(), "Across clues do not match the grid"),
    (lambda d: d["clues"]["Down"].append([9, "extra"]), "no such word \\[9\\]"),
    (lambda d: d["clues"]["Across"].append([1, "again"]), "appears twice"),
    (lambda d: d["clues"]["Across"].__setitem__(0, [1, "  "]), "has no text"),
    (lambda d: d["clues"]["Across"].__setitem__(0, "Top"), "must look like"),
    (lambda d: d["clues"].pop("Down"), "no \\\"Down\\\" list"),
    (lambda d: d.pop("clues"), "\\\"clues\\\" must have"),
])
def test_broken_puzzles_are_messages_naming_the_file(tmp_path, mutate, match):
    doc = json.loads(json.dumps(RING))
    mutate(doc)
    with pytest.raises(B.BuildError, match=match):
        B.read_ipuz(write(tmp_path, doc, "bad.ipuz"), "post.html")


def test_invalid_json_and_a_non_object_are_messages(tmp_path):
    for text, match in (("{not json", "not valid JSON"), ("[1, 2]", "must contain a JSON object")):
        with pytest.raises(B.BuildError, match=match):
            B.read_ipuz(write(tmp_path, text, "x.ipuz"), "post.html")


# ---- the shortcode and the page --------------------------------------------------------------------------------------------------------
def site_with_puzzle(tmp, doc=RING, body="<p>Intro</p>\n{{crossword p.ipuz}}", **over):
    site = make_site(tmp, posts={"a.html": post(body=body)}, pages={"about.html": ABOUT}, **over)
    folder = site / "content" / "posts" / "a"
    folder.mkdir()
    write(folder, doc)
    return site


def build_page(site, **kw):
    out = site / "public"
    B.build(site, out, **kw)
    return out, (out / "a" / "index.html").read_text(encoding="utf-8")


def test_the_shortcode_writes_the_player_markup_and_the_script_with_a_relative_path(tmp_path):
    out, page = build_page(site_with_puzzle(tmp_path))
    assert re.search(r'<div class="crossword wide" data-id="[0-9a-f]{12}"><p class="cw-meta"><b>Ring</b> by A. Setter</p>', page)
    assert '<script src="../theme/crossword.js" defer></script>' in page and (out / "theme" / "crossword.js").exists()
    assert '<noscript><p>This crossword needs JavaScript' in page and '<li value="1">Top</li>' in page
    assert B.check_links(out) == []
    data = json.loads(re.search(r'<script type="application/json" class="crossword-data">(.*?)</script>', page, re.S).group(1))
    assert data["grid"] == ["ABC", "D#E", "FGH"] and data["across"][0] == [1, "Top"]


def test_nothing_in_a_puzzle_can_close_the_data_block_or_inject_markup(tmp_path):
    nasty = '</script><img src=x onerror="alert(1)"> & <b>'
    doc = ipuz(["ABC", "D#E", "FGH"], {1: nasty, 3: "Bottom"}, {1: "Left", 2: "Right"}, title=nasty, author=nasty)
    out, page = build_page(site_with_puzzle(tmp_path, doc))
    assert "<img src=x" not in page and "onerror=\"alert(1)\">" not in page
    block = re.search(r'<script type="application/json" class="crossword-data">(.*?)</script>', page, re.S).group(1)
    assert "<" not in block and ">" not in block and json.loads(block)["title"] == nasty               # decodes back to the original text
    assert "&lt;/script&gt;&lt;img" in page                                                             # the visible title and clues are escaped


@pytest.mark.parametrize("call,match", [
    ("{{crossword missing.ipuz}}", "needs the name of an .ipuz file"),
    ("{{crossword ../a.html}}", "needs the name of an .ipuz file"),
    ("{{crossword ../../site.json}}", "needs the name of an .ipuz file"),
    ("{{crossword}}", "needs the name of an .ipuz file"),
    ("{{#crossword}}x{{/crossword}}", "does not wrap content"),
])
def test_shortcode_mistakes_are_messages(tmp_path, call, match):
    site = site_with_puzzle(tmp_path, body=call)
    with pytest.raises(B.BuildError, match=match):
        B.build(site, site / "public")


def test_the_shortcode_is_refused_in_the_home_page_intro(tmp_path):
    site = site_with_puzzle(tmp_path, intro="<p>{{crossword p.ipuz}}</p>")
    with pytest.raises(B.BuildError, match="works in posts and pages"):
        B.build(site, site / "public")


def test_a_puzzle_error_names_the_post(tmp_path):
    site = site_with_puzzle(tmp_path, doc="{broken")
    with pytest.raises(B.BuildError, match=r"a\.html: crossword: p\.ipuz is not valid JSON"):
        B.build(site, site / "public")


def test_the_shortcode_is_listed_among_the_available_pieces(tmp_path):
    site = site_with_puzzle(tmp_path, body="{{nope}}")
    with pytest.raises(B.BuildError, match="crossword"):
        B.build(site, site / "public")


def test_the_shortcode_inside_code_is_shown_as_text_not_expanded(tmp_path):
    out, page = build_page(site_with_puzzle(tmp_path, body="<p><code>{{crossword p.ipuz}}</code></p>"))
    assert "{{crossword p.ipuz}}" in page and 'class="crossword' not in page


# ---- sections: no reading time for puzzles ---------------------------------------------------------------------------------------------------
def test_a_section_can_switch_off_the_reading_time_row(tmp_path):
    secs = [{"id": "crosswords", "heading": "Crosswords", "reading_time": False}]
    site = make_site(tmp_path, posts={"a.html": post(section="crosswords"), "b.html": post(title="B")}, sections=secs, pages={"about.html": ABOUT})
    B.build(site, site / "public")
    assert "Reading time" not in (site / "public" / "a" / "index.html").read_text(encoding="utf-8")
    assert "Reading time" in (site / "public" / "b" / "index.html").read_text(encoding="utf-8")


def test_reading_time_must_be_true_or_false(tmp_path):
    with pytest.raises(B.BuildError, match="'reading_time' must be true or false"):
        B.load_site(make_site(tmp_path, sections=[{"id": "x", "heading": "X", "reading_time": "no"}]))


# ---- the player itself (no JavaScript runtime here: check the contract between page, script and styles) -------------------------------------------
def test_the_player_script_and_styles_exist_and_agree_on_the_class_names():
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    classes = set(re.findall(r"cw-[a-z]+(?:-[a-z]+)*", js))                    # every class the script mentions
    missing = sorted(c for c in classes if f".{c}" not in css)
    assert not missing, missing
    assert "script.crossword-data" in js and "blog-crossword:" in js and "localStorage" in js


def test_the_player_never_writes_data_as_html():
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "eval(" not in js and "document.write" not in js


def test_the_finishing_flourish_is_switched_off_for_readers_who_ask_for_less_motion_and_only_follows_a_clean_solve():
    css = (ROOT / "theme" / "style.css").read_text(encoding="utf-8")
    assert re.search(r"@media \(prefers-reduced-motion:reduce\)\{[^}]*\.cw-wave[^}]*animation:none", css)
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    assert "helpedCount() === 0" in js and "cw-solved" in js and "cw-wave" in js                  # no celebration when squares were revealed


def test_open_menus_close_on_an_outside_click_escape_tab_away_and_when_the_other_opens():
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    assert "document.addEventListener('click'" in js and "m.contains(e.target)" in js
    assert "e.key === 'Escape') closeMenus" in js and "addEventListener('focusout'" in js and "addEventListener('toggle'" in js


def test_clear_asks_again_on_the_button_instead_of_a_browser_pop_up_that_some_browsers_swallow():
    js = (ROOT / "theme" / "crossword.js").read_text(encoding="utf-8")
    assert "confirm(" not in js and "alert(" not in js and "Sure? Clear" in js
