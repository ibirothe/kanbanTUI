from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from kanban_tui.config import validate_config


@pytest.fixture(autouse=True)
def isolated_app_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KANBAN_TUI_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def write_config(isolated_app_home):
    def _write(*, limits=None, repaint=False, data_path: Path | None = None):
        raw = {
            "data_path": str(data_path or (isolated_app_home / ".kanban-tui.dat")),
            "repaint": repaint,
        }
        if limits is not None:
            raw["limits"] = limits

        config_path = isolated_app_home / ".kanban-tui.yaml"
        config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return validate_config(raw, config_path)

    return _write
