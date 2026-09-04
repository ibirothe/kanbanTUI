from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from kanban_tui.config import validate_config


@pytest.fixture(autouse=True)
def isolated_clikan_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def write_config(isolated_clikan_home):
    def _write(*, limits=None, repaint=False, data_path: Path | None = None):
        raw = {
            "clikan_data": str(data_path or (isolated_clikan_home / ".clikan.dat")),
            "repaint": repaint,
        }
        if limits is not None:
            raw["limits"] = limits

        config_path = isolated_clikan_home / ".clikan.yaml"
        config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        return validate_config(raw, config_path)

    return _write
