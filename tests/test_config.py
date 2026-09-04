from pathlib import Path

import click
import pytest
import yaml

from kanban_tui.config import (
    create_default_config,
    get_config_path,
    read_config,
    validate_config,
)


def test_config_defaults_are_normalized(tmp_path):
    config = validate_config(
        {"clikan_data": str(tmp_path / ".clikan.dat")},
        tmp_path / ".clikan.yaml",
    )

    assert config.limits.taskname == 40
    assert config.limits.done == 10
    assert config.repaint is False


def test_absolute_data_path_is_preserved(tmp_path):
    data_path = tmp_path / "board.dat"

    config = validate_config(
        {"clikan_data": str(data_path)},
        tmp_path / ".clikan.yaml",
    )

    assert config.clikan_data == data_path


def test_relative_data_path_resolves_against_config_directory(tmp_path):
    config_dir = tmp_path / "config"
    config_path = config_dir / ".clikan.yaml"

    config = validate_config({"clikan_data": "./data/board.dat"}, config_path)

    assert config.clikan_data == (config_dir / "data" / "board.dat").resolve()


def test_tilde_data_path_is_expanded(tmp_path):
    config = validate_config(
        {"clikan_data": "~/board.dat"},
        tmp_path / ".clikan.yaml",
    )

    assert config.clikan_data == Path("~/board.dat").expanduser()


def test_explicit_config_path_overrides_clikan_home(monkeypatch, tmp_path):
    default_home = tmp_path / "default-home"
    explicit_path = tmp_path / "boards" / "work.yaml"
    monkeypatch.setenv("CLIKAN_HOME", str(default_home))

    assert get_config_path(explicit_path) == explicit_path.resolve()
    assert get_config_path() == (default_home / ".clikan.yaml").resolve()


def test_read_explicit_config_uses_its_directory_for_relative_data(tmp_path):
    config_path = tmp_path / "boards" / "work.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump({"clikan_data": "./work.dat"}),
        encoding="utf-8",
    )

    config = read_config(config_path)

    assert config.clikan_data == (config_path.parent / "work.dat").resolve()


def test_invalid_limit_is_rejected(tmp_path):
    with pytest.raises(click.ClickException, match="non-negative integer"):
        validate_config(
            {
                "clikan_data": str(tmp_path / ".clikan.dat"),
                "limits": {"wip": -1},
            },
            tmp_path / ".clikan.yaml",
        )


def test_missing_config_returns_nonzero_cli_error(runner):
    from kanban_tui.cli import clikan

    result = runner.invoke(clikan, ["show"])

    assert result.exit_code != 0
    assert "Could not read config file" in result.output


def test_read_config_parses_yaml(isolated_clikan_home):
    path = get_config_path()
    path.write_text(
        yaml.safe_dump(
            {
                "clikan_data": str(isolated_clikan_home / ".clikan.dat"),
                "limits": {"wip": "2"},
            }
        ),
        encoding="utf-8",
    )

    config = read_config()

    assert config.limits.wip == 2


def test_create_default_config_creates_missing_home(monkeypatch, tmp_path):
    nested_home = tmp_path / "nested" / "clikan-home"
    monkeypatch.setenv("CLIKAN_HOME", str(nested_home))

    config_path = create_default_config()

    assert config_path == nested_home / ".clikan.yaml"
    assert config_path.exists()


def test_create_default_config_at_explicit_path(tmp_path):
    config_path = tmp_path / "boards" / "personal.yaml"

    created_path = create_default_config(config_path)
    raw = yaml.safe_load(created_path.read_text(encoding="utf-8"))

    assert created_path == config_path.resolve()
    assert raw["clikan_data"] == str(config_path.resolve().with_suffix(".dat"))
