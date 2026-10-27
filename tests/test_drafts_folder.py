"""content/drafts/: work in progress that is built for you but never published."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B  # noqa: E402
from test_build import make_site, post  # noqa: E402


def with_draft(tmp):
    make_site(tmp, nav=[], posts={"live.html": post("Live", "2026-01-02")})
    d = tmp / "content" / "drafts"
    d.mkdir(parents=True)
    (d / "wip.html").write_text(post("Work in progress", "2026-03-04", draft="false", body='<video src="assets/c.mp4"></video>'), encoding="utf-8")
    (d / "wip").mkdir()
    (d / "wip" / "assets").mkdir()
    (d / "wip" / "assets" / "c.mp4").write_text("v", encoding="utf-8")


def test_a_draft_is_built_for_you_with_its_folder_even_if_it_says_draft_false(tmp_path):
    with_draft(tmp_path)
    B.build(tmp_path, tmp_path / "dev")
    home = (tmp_path / "dev" / "index.html").read_text(encoding="utf-8")
    assert "Work in progress" in home and "draft</span>" in home and (tmp_path / "dev" / "wip" / "assets" / "c.mp4").exists()
    assert B.check_links(tmp_path / "dev") == []


def test_nothing_from_the_drafts_folder_is_published(tmp_path):
    with_draft(tmp_path)
    B.build(tmp_path, tmp_path / "pub", publish=True)
    assert not (tmp_path / "pub" / "wip").exists()
    for f in (tmp_path / "pub").rglob("*"):
        if f.is_file() and f.suffix in {".html", ".xml"}:
            assert "Work in progress" not in f.read_text(encoding="utf-8"), f
    assert B.check_links(tmp_path / "pub") == []


def test_a_draft_may_not_reuse_the_address_of_a_post(tmp_path):
    with_draft(tmp_path)
    (tmp_path / "content" / "drafts" / "live.html").write_text(post("Same address"), encoding="utf-8")
    import pytest
    with pytest.raises(B.BuildError, match="already used"):
        B.build(tmp_path, tmp_path / "out")
