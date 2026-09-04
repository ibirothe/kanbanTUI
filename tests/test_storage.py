from pathlib import Path

import click
import pytest
import yaml

from kanban_tui.models import Board, Task, TaskState
from kanban_tui.storage import datastore_lock, read_data, write_data


def test_missing_datastore_is_initialized(write_config, isolated_clikan_home):
    config = write_config()

    with datastore_lock(config):
        board = read_data(config)

    assert board == Board()
    assert (isolated_clikan_home / ".clikan.dat").exists()


def test_write_data_round_trip(write_config):
    config = write_config()
    board = Board(
        active={
            1: Task(
                id=1,
                state=TaskState.TODO,
                text="task",
                modified_at="now",
                created_at="before",
            )
        }
    )

    with datastore_lock(config):
        write_data(config, board)
        loaded = read_data(config)

    assert loaded == board


def test_existing_lock_is_rejected(write_config):
    config = write_config()
    lock_path = Path(f"{config.clikan_data}.lock")
    lock_path.mkdir()

    with pytest.raises(click.ClickException, match="locked by another clikan process"):
        with datastore_lock(config):
            pass


def test_legacy_yaml_format_is_deserialized(write_config):
    config = write_config()
    config.clikan_data.write_text(
        yaml.safe_dump(
            {
                "data": {1: ["todo", "task", "now", "before"]},
                "deleted": {},
            }
        ),
        encoding="utf-8",
    )

    with datastore_lock(config):
        board = read_data(config)

    assert board.active[1].state is TaskState.TODO
    assert board.active[1].text == "task"


def test_invalid_datastore_record_is_rejected(write_config):
    config = write_config()
    config.clikan_data.write_text(
        yaml.safe_dump({"data": {1: ["todo"]}, "deleted": {}}),
        encoding="utf-8",
    )

    with datastore_lock(config):
        with pytest.raises(click.ClickException, match="invalid record"):
            read_data(config)
