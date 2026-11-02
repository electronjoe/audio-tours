import subprocess
import tomllib
from datetime import date

import pytest

from audiotour import new
from audiotour.config import REPO_ROOT, Tour
from audiotour.script import check_file, load_tracks
from audiotour.spend import Guard

TITLE = 'Hobart to "Bruny" Island'


def make(tmp_path):
    return new.create("bruny", TITLE, tours_dir=tmp_path, today=date(2026, 11, 4))


def test_new_writes_every_template_filled_in(tmp_path):
    paths = make(tmp_path)
    assert [p.relative_to(tmp_path / "bruny").as_posix() for p in paths] == list(new.FILES.values())
    for p in paths:
        assert "${" not in p.read_text(), p
    settings = tomllib.loads((tmp_path / "bruny" / "tour.toml").read_text())
    assert settings["tour"]["title"] == TITLE and settings["tour"]["year"] == 2026
    assert settings["player"] == {"mode": "drive", "lookahead": 2}
    assert "route" not in settings and "stops" not in settings  # left as commented examples
    assert "2026-11-04" in (tmp_path / "bruny" / "source" / "research.md").read_text()


def test_new_draft_parses_with_no_tracks(tmp_path):
    make(tmp_path)
    tour = Tour("bruny", tours_dir=tmp_path)
    assert load_tracks(tour.draft) == []
    [problem] = check_file(tour.draft, tour.settings)
    assert problem.error and "no" in problem.message.lower()


def test_new_research_notes_are_gitignored_and_the_rest_is_not():
    def ignored(rel):
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", rel], cwd=REPO_ROOT).returncode == 0

    assert ignored("tours/bruny/source/research.md")
    for rel in ("tour.toml", "plan.md", "source/working-draft.md"):
        assert not ignored(f"tours/bruny/{rel}"), rel


@pytest.mark.parametrize("slug", ["Bruny", "bruny_island", "-bruny", "player", "lab"])
def test_new_refuses_bad_or_reserved_slugs(tmp_path, slug):
    with pytest.raises(SystemExit):
        new.create(slug, "X", tours_dir=tmp_path)
    assert not any(tmp_path.iterdir())


def test_new_never_overwrites(tmp_path):
    make(tmp_path)
    toml = tmp_path / "bruny" / "tour.toml"
    toml.write_text("# edited\n")
    with pytest.raises(SystemExit, match="already exists"):
        make(tmp_path)
    assert toml.read_text() == "# edited\n"


def test_guard_notes_a_test_only_tour(tmp_path, capsys):
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "tour.toml").write_text("[tour]\ntitle = 'T'\ntest_only = true\n")
    Guard(Tour("t", tours_dir=tmp_path), assume_yes=True).approve("render stop-1", 10)
    assert "test-only" in capsys.readouterr().out


def test_hobart_is_test_only():
    assert Tour("hobart").info.get("test_only") is True
