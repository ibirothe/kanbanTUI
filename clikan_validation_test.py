from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from clikan import clikan, read_config_yaml


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIKAN_HOME", str(tmp_path))
    return tmp_path


def write_config(home, config):
    (home / ".clikan.yaml").write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )


def valid_config(home):
    return {"clikan_data": str(home / ".clikan.dat")}


def write_board(home, board):
    (home / ".clikan.dat").write_text(
        yaml.safe_dump(board),
        encoding="utf-8",
    )


def test_missing_config_returns_nonzero(isolated_home):
    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert "Could not read config file" in result.output


def test_invalid_config_yaml_returns_nonzero(isolated_home):
    (isolated_home / ".clikan.yaml").write_text("limits: [", encoding="utf-8")

    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert "contains invalid YAML" in result.output


@pytest.mark.parametrize(
    "config, expected_message",
    [
        ([], "must contain a YAML mapping"),
        ({}, "must define a non-empty clikan_data path"),
        ({"clikan_data": "board.yaml", "limits": []}, "limits must be a mapping"),
        (
            {"clikan_data": "board.yaml", "limits": {"wip": "many"}},
            "limits.wip must be a non-negative integer",
        ),
        (
            {"clikan_data": "board.yaml", "limits": {"wip": -1}},
            "limits.wip must be a non-negative integer",
        ),
        (
            {"clikan_data": "board.yaml", "repaint": "yes"},
            "repaint must be true or false",
        ),
    ],
)
def test_invalid_config_schema_returns_nonzero(
    isolated_home,
    config,
    expected_message,
):
    write_config(isolated_home, config)

    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert expected_message in result.output


def test_partial_config_receives_defaults(isolated_home):
    write_config(isolated_home, valid_config(isolated_home))

    config = read_config_yaml()

    assert config["limits"]["taskname"] == 40
    assert config["limits"]["done"] == 10
    assert "todo" not in config["limits"]
    assert "wip" not in config["limits"]
    assert config["repaint"] is False


def test_empty_datastore_returns_nonzero(isolated_home):
    write_config(isolated_home, valid_config(isolated_home))
    (isolated_home / ".clikan.dat").write_text("", encoding="utf-8")

    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert "must contain a YAML mapping" in result.output


def test_invalid_datastore_yaml_returns_nonzero(isolated_home):
    write_config(isolated_home, valid_config(isolated_home))
    (isolated_home / ".clikan.dat").write_text("data: [", encoding="utf-8")

    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert "contains invalid YAML" in result.output


@pytest.mark.parametrize(
    "board, expected_message",
    [
        ({"data": {}}, "must contain data and deleted mappings"),
        (
            {"data": [], "deleted": {}},
            "data must be a mapping",
        ),
        (
            {
                "data": {1: ["unknown", "task", "now", "created"]},
                "deleted": {},
            },
            "unsupported state",
        ),
        (
            {
                "data": {"1": ["todo", "task", "now", "created"]},
                "deleted": {},
            },
            "task ids in data must be positive integers",
        ),
        (
            {
                "data": {1: ["todo"]},
                "deleted": {},
            },
            "has an invalid record",
        ),
    ],
)
def test_invalid_datastore_schema_returns_nonzero(
    isolated_home,
    board,
    expected_message,
):
    write_config(isolated_home, valid_config(isolated_home))
    write_board(isolated_home, board)

    result = CliRunner().invoke(clikan, ["show"])

    assert result.exit_code == 1
    assert expected_message in result.output
