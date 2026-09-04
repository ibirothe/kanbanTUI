from pathlib import Path

import pytest
import yaml

from kanban_tui.storage import datastore_lock, read_data, validate_data, write_data


def test_missing_datastore_is_initialized(write_config, isolated_clikan_home):
    config = write_config()

    with datastore_lock(config):
        data = read_data(config)

    assert data == {"data": {}, "deleted": {}}
    assert (isolated_clikan_home / ".clikan.dat").exists()


def test_write_data_round_trip(write_config):
    config = write_config()
    data = {
        "data": {1: ["todo", "task", "now", "before"]},
        "deleted": {},
    }

    with datastore_lock(config):
        write_data(config, data)
        loaded = read_data(config)

    assert loaded == data


def test_existing_lock_is_rejected(write_config):
    config = write_config()
    lock_path = Path(config["clikan_data"] + ".lock")
    lock_path.mkdir()

    with pytest.raises(Exception, match="locked by another clikan process"):
        with datastore_lock(config):
            pass


def test_invalid_datastore_record_is_rejected(tmp_path):
    with pytest.raises(Exception, match="invalid record"):
        validate_data(
            {"data": {1: ["todo"]}, "deleted": {}},
            tmp_path / ".clikan.dat",
        )
