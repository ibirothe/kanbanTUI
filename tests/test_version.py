from pathlib import Path

from kanban_tui import VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_source_version_matches_version_file():
    assert VERSION == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
