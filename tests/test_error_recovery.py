import os
import subprocess
import sys
from functools import partial
from pathlib import Path

import click
import pytest

from kanban_tui.atomic import atomic_text_writer
from kanban_tui.cli import ThemeParamType, main
from kanban_tui.config import get_config_path, read_config, write_config_document
from kanban_tui.models import Board
from kanban_tui.storage import read_data
from kanban_tui.themes import get_theme, get_user_theme_dir
from kanban_tui.transfer import read_export


@pytest.mark.parametrize("command", ["--help", "--version"])
def test_cli_startup_ignores_invalid_theme_filename(command):
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True)
    (theme_dir / "Bad Name.yaml").write_text("extends: arch\n")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run(
        [sys.executable, "-c", "from kanban_tui.cli import main; main()", command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


def test_theme_completion_discovers_files_created_after_parameter():
    parameter = ThemeParamType()
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True)
    (theme_dir / "ocean.yaml").write_text("extends: arch\n")
    assert [item.value for item in parameter.shell_complete(None, None, "oc")] == [
        "ocean"
    ]


@pytest.mark.parametrize(
    "command", [["config", "set", "theme", "arch"], ["theme", "set", "arch"]]
)
@pytest.mark.parametrize("broken", ["missing", "invalid"])
def test_repair_selected_theme(runner, write_config, command, broken):
    write_config()
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True)
    theme_path = theme_dir / "ocean.yaml"
    theme_path.write_text("extends: arch\n")
    assert runner.invoke(main, ["config", "set", "theme", "ocean"]).exit_code == 0
    if broken == "missing":
        theme_path.unlink()
    else:
        theme_path.write_text("colors: {accent: bad}\n")
    original = get_config_path().read_bytes()
    assert runner.invoke(main, ["config", "set", "theme", "nonexistent"]).exit_code != 0
    assert get_config_path().read_bytes() == original
    assert runner.invoke(main, command).exit_code == 0
    assert read_config().theme == "arch"


@pytest.mark.parametrize("kind", ["config", "datastore", "theme", "import"])
def test_invalid_utf8_is_contextual(kind, write_config, tmp_path):
    config = write_config()
    if kind == "config":
        path, reader = get_config_path(), read_config
    elif kind == "datastore":
        path, reader = config.data_path, partial(read_data, config)
    elif kind == "theme":
        path = get_user_theme_dir() / "ocean.yaml"
        path.parent.mkdir(parents=True)
        reader = partial(get_theme, "ocean")
    else:
        path = tmp_path / "import.json"
        reader = partial(read_export, path)
    path.write_bytes(b"\xff")
    with pytest.raises(click.ClickException, match="UTF-8") as error:
        reader()
    assert str(path) in str(error.value)
    assert path.read_bytes() == b"\xff"


@pytest.mark.parametrize("failure", ["serialize", "fsync", "replace"])
def test_atomic_failure_preserves_destination_and_cleans_temp(
    tmp_path, monkeypatch, failure
):
    path = tmp_path / "original.yaml"
    path.write_text("original")

    def fail(*args):
        raise OSError("simulated failure")

    if failure != "serialize":
        monkeypatch.setattr(f"kanban_tui.atomic.os.{failure}", fail)
    with pytest.raises(OSError, match="simulated failure"):
        with atomic_text_writer(path) as stream:
            stream.write("replacement")
            if failure == "serialize":
                fail()
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_config_parent_failure_is_contextual(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("not a directory")
    with pytest.raises(click.ClickException, match="Could not write config"):
        write_config_document(
            {"data_path": str(tmp_path / "board")}, parent / "config.yaml"
        )


def test_cleanup_failure_preserves_original_error(tmp_path, monkeypatch):
    def fail_unlink(*args, **kwargs):
        raise OSError("cleanup failed")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(ValueError, match="original failure"):
            with atomic_text_writer(tmp_path / "output"):
                raise ValueError("original failure")


def test_flush_failure_removes_temporary_file(tmp_path, monkeypatch):
    from kanban_tui import atomic

    create = atomic.tempfile.NamedTemporaryFile

    def failing_file(*args, **kwargs):
        stream = create(*args, **kwargs)

        def fail():
            raise OSError("flush failed")

        stream.flush = fail
        return stream

    monkeypatch.setattr(atomic.tempfile, "NamedTemporaryFile", failing_file)
    with pytest.raises(OSError, match="flush failed"):
        with atomic_text_writer(tmp_path / "output") as stream:
            stream.write("pending")
    assert list(tmp_path.iterdir()) == []


def test_config_repair_preserves_unknown_fields_and_validates_other_settings(
    runner, write_config
):
    import yaml

    write_config()
    path = get_config_path()
    raw = yaml.safe_load(path.read_text())
    raw.update(theme="missing", custom_field={"keep": "value"})
    path.write_text(yaml.safe_dump(raw))
    assert runner.invoke(main, ["config", "set", "theme", "arch"]).exit_code == 0
    assert yaml.safe_load(path.read_text())["custom_field"] == {"keep": "value"}
    raw.update(limits={"wip": -1})
    path.write_text(yaml.safe_dump(raw))
    original = path.read_bytes()
    assert runner.invoke(main, ["config", "set", "theme", "arch"]).exit_code != 0
    assert path.read_bytes() == original


def test_invalid_import_does_not_change_board_or_undo(runner, write_config, tmp_path):
    config = write_config()
    runner.invoke(main, ["add", "existing"])
    original = config.data_path.read_bytes()
    path = tmp_path / "bad.json"
    path.write_bytes(b"\xff")
    result = runner.invoke(main, ["import", str(path)])
    assert result.exit_code == 1
    assert "UTF-8" in result.output
    assert config.data_path.read_bytes() == original
    assert runner.invoke(main, ["undo"]).exit_code == 0
    assert read_data(config) == Board()
