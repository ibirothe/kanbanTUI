from pathlib import Path

import click
import pytest
import yaml
from click.testing import CliRunner

import clikan as clikan_module
from clikan import clikan, datastore_lock, write_data


@pytest.fixture
def storage_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    config = {"clikan_data": str(tmp_path / ".clikan.dat")}
    (tmp_path / ".clikan.yaml").write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )
    return tmp_path, config


def empty_board():
    return {"data": {}, "deleted": {}}


def board_with_task(text):
    return {
        "data": {1: ["todo", text, "now", "created"]},
        "deleted": {},
    }


def test_datastore_lock_blocks_second_holder_and_cleans_up(storage_home):
    home, config = storage_home
    lock_path = Path(config["clikan_data"] + ".lock")

    with datastore_lock(config):
        assert lock_path.is_dir()
        with pytest.raises(click.ClickException, match="is locked"):
            with datastore_lock(config):
                pass

    assert not lock_path.exists()


def test_mutating_command_is_blocked_while_lock_is_held(storage_home):
    home, config = storage_home
    runner = CliRunner()

    with datastore_lock(config):
        result = runner.invoke(clikan, ["add", "blocked task"])

    assert result.exit_code == 1
    assert "is locked by another clikan process" in result.output
    assert not Path(config["clikan_data"]).exists()

    result = runner.invoke(clikan, ["add", "allowed task"])
    assert result.exit_code == 0

    board = yaml.safe_load(
        Path(config["clikan_data"]).read_text(encoding="utf-8")
    )
    assert board["data"][1][1] == "allowed task"


def test_atomic_write_replaces_datastore(storage_home):
    home, config = storage_home
    write_data(config, empty_board())

    write_data(config, board_with_task("new state"))

    board = yaml.safe_load(
        Path(config["clikan_data"]).read_text(encoding="utf-8")
    )
    assert board == board_with_task("new state")
    assert list(home.glob(".clikan-*.tmp")) == []


def test_atomic_write_failure_preserves_previous_datastore(
    storage_home,
    monkeypatch,
):
    home, config = storage_home
    data_path = Path(config["clikan_data"])
    previous = board_with_task("previous state")
    data_path.write_text(yaml.safe_dump(previous), encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(clikan_module.os, "replace", fail_replace)

    with pytest.raises(click.ClickException, match="Could not write datastore"):
        write_data(config, board_with_task("new state"))

    board = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    assert board == previous
    assert list(home.glob(".clikan-*.tmp")) == []
