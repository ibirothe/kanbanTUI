from datetime import datetime, timezone

import click
import pytest
import yaml

from kanban_tui.models import Board, Task, TaskState
from kanban_tui.storage import datastore_lock, read_data, write_data


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def test_missing_datastore_read_is_side_effect_free(write_config, capsys):
    config = write_config()

    board = read_data(config)

    assert board == Board()
    assert not config.data_path.exists()
    assert capsys.readouterr().out == ""


def test_missing_datastore_read_does_not_create_parent(write_config, tmp_path):
    data_path = tmp_path / "nested" / "boards" / "board.dat"
    config = write_config(data_path=data_path)

    board = read_data(config)

    assert board == Board()
    assert not data_path.exists()
    assert not data_path.parent.exists()


def test_write_data_round_trip_uses_iso_timestamps(write_config):
    config = write_config()
    board = Board(
        active={
            1: Task(
                id=1,
                state=TaskState.TODO,
                text="task",
                modified_at=NOW,
                created_at=BEFORE,
            )
        }
    )

    with datastore_lock(config):
        write_data(config, board)
        loaded = read_data(config)

    raw = yaml.safe_load(config.data_path.read_text(encoding="utf-8"))
    assert loaded == board
    assert raw["data"][1][2] == "2026-09-04T10:00:00+00:00"
    assert raw["data"][1][3] == "2026-09-04T09:00:00+00:00"


def test_concurrent_writer_lock_is_rejected(write_config):
    config = write_config()

    with datastore_lock(config):
        with pytest.raises(click.ClickException, match="locked by another kanban-tui process"):
            with datastore_lock(config):
                pass


def test_writer_lock_can_be_reacquired_after_release(write_config):
    config = write_config()

    with datastore_lock(config):
        pass

    with datastore_lock(config):
        pass


def test_lock_is_released_after_exception(write_config):
    config = write_config()

    with pytest.raises(RuntimeError, match="boom"):
        with datastore_lock(config):
            raise RuntimeError("boom")

    with datastore_lock(config):
        pass


def test_initialize_missing_flag_no_longer_changes_read_behavior(write_config):
    config = write_config()

    board = read_data(config, initialize_missing=True)

    assert board == Board()
    assert not config.data_path.exists()


def test_older_timestamp_format_is_deserialized(write_config):
    config = write_config()
    config.data_path.write_text(
        yaml.safe_dump(
            {
                "data": {
                    1: [
                        "todo",
                        "task",
                        "2026-Sep-04 10:00:00",
                        "2026-Sep-04 09:00:00",
                    ]
                },
                "deleted": {},
            }
        ),
        encoding="utf-8",
    )

    with datastore_lock(config):
        board = read_data(config)

    assert board.active[1].state is TaskState.TODO
    assert board.active[1].text == "task"
    assert board.active[1].modified_at.tzinfo is not None


def test_invalid_datastore_record_is_rejected(write_config):
    config = write_config()
    config.data_path.write_text(
        yaml.safe_dump({"data": {1: ["todo"]}, "deleted": {}}),
        encoding="utf-8",
    )

    with datastore_lock(config):
        with pytest.raises(click.ClickException, match="invalid record"):
            read_data(config)
