from pathlib import Path

import click
import pytest
import yaml

from kanban_tui.config import (
    create_default_config,
    create_named_board,
    get_board_config_path,
    get_config_path,
    read_config,
    validate_config,
)


def test_config_defaults_are_normalized(tmp_path):
    config = validate_config(
        {"data_path": str(tmp_path / ".kanban-tui.dat")},
        tmp_path / ".kanban-tui.yaml",
    )

    assert config.limits.taskname == 40
    assert config.limits.done == 10
    assert config.repaint is False


def test_absolute_data_path_is_preserved(tmp_path):
    data_path = tmp_path / "board.dat"

    config = validate_config(
        {"data_path": str(data_path)},
        tmp_path / ".kanban-tui.yaml",
    )

    assert config.data_path == data_path


def test_relative_data_path_resolves_against_config_directory(tmp_path):
    config_dir = tmp_path / "config"
    config_path = config_dir / ".kanban-tui.yaml"

    config = validate_config({"data_path": "./data/board.dat"}, config_path)

    assert config.data_path == (config_dir / "data" / "board.dat").resolve()


def test_tilde_data_path_is_expanded(tmp_path):
    config = validate_config(
        {"data_path": "~/board.dat"},
        tmp_path / ".kanban-tui.yaml",
    )

    assert config.data_path == Path("~/board.dat").expanduser().resolve()


def test_data_path_cannot_point_to_config_file(tmp_path):
    config_path = tmp_path / "board.yaml"

    with pytest.raises(click.ClickException, match="must not point to the config file itself"):
        validate_config({"data_path": str(config_path)}, config_path)


def test_explicit_config_path_overrides_app_home(monkeypatch, tmp_path):
    default_home = tmp_path / "default-home"
    explicit_path = tmp_path / "boards" / "work.yaml"
    monkeypatch.setenv("KANBAN_TUI_HOME", str(default_home))

    assert get_config_path(explicit_path) == explicit_path.resolve()
    assert get_config_path() == (default_home / ".kanban-tui.yaml").resolve()


def test_xdg_paths_are_default_without_portable_home(monkeypatch, tmp_path):
    xdg_config = tmp_path / "xdg-config"
    xdg_data = tmp_path / "xdg-data"
    monkeypatch.delenv("KANBAN_TUI_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    created = create_default_config()
    raw = yaml.safe_load(created.read_text(encoding="utf-8"))

    assert created == (xdg_config / "kanban-tui" / "config.yaml").resolve()
    assert raw["data_path"] == str(
        (xdg_data / "kanban-tui" / "board.dat").resolve()
    )


def test_existing_legacy_default_config_is_discovered(monkeypatch, tmp_path):
    home = tmp_path / "home"
    xdg_config = tmp_path / "xdg-config"
    home.mkdir()
    legacy = home / ".kanban-tui.yaml"
    legacy.write_text(yaml.safe_dump({"data_path": "./legacy.dat"}), encoding="utf-8")

    monkeypatch.delenv("KANBAN_TUI_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    assert get_config_path() == legacy.resolve()
    assert read_config().data_path == (home / "legacy.dat").resolve()


def test_xdg_named_board_separates_config_and_data(monkeypatch, tmp_path):
    xdg_config = tmp_path / "xdg-config"
    xdg_data = tmp_path / "xdg-data"
    monkeypatch.delenv("KANBAN_TUI_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    created = create_named_board("work")
    raw = yaml.safe_load(created.read_text(encoding="utf-8"))

    assert created == (xdg_config / "kanban-tui" / "boards" / "work.yaml").resolve()
    assert get_board_config_path("work") == created
    assert raw["data_path"] == str(
        (xdg_data / "kanban-tui" / "boards" / "work.dat").resolve()
    )


def test_read_explicit_config_uses_its_directory_for_relative_data(tmp_path):
    config_path = tmp_path / "boards" / "work.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump({"data_path": "./work.dat"}),
        encoding="utf-8",
    )

    config = read_config(config_path)

    assert config.data_path == (config_path.parent / "work.dat").resolve()


def test_invalid_limit_is_rejected(tmp_path):
    with pytest.raises(click.ClickException, match="non-negative integer"):
        validate_config(
            {
                "data_path": str(tmp_path / ".kanban-tui.dat"),
                "limits": {"wip": -1},
            },
            tmp_path / ".kanban-tui.yaml",
        )


def test_fractional_limit_is_rejected_instead_of_truncated(tmp_path):
    with pytest.raises(click.ClickException, match="non-negative integer"):
        validate_config(
            {
                "data_path": str(tmp_path / ".kanban-tui.dat"),
                "limits": {"wip": 1.5},
            },
            tmp_path / ".kanban-tui.yaml",
        )


def test_missing_config_returns_nonzero_cli_error(runner):
    from kanban_tui.cli import main

    result = runner.invoke(main, ["show"])

    assert result.exit_code != 0
    assert "Could not read config file" in result.output


def test_read_config_parses_yaml(isolated_app_home):
    path = get_config_path()
    path.write_text(
        yaml.safe_dump(
            {
                "data_path": str(isolated_app_home / ".kanban-tui.dat"),
                "limits": {"wip": "2"},
            }
        ),
        encoding="utf-8",
    )

    config = read_config()

    assert config.limits.wip == 2


def test_create_default_config_creates_missing_home(monkeypatch, tmp_path):
    nested_home = tmp_path / "nested" / "kanban-home"
    monkeypatch.setenv("KANBAN_TUI_HOME", str(nested_home))

    config_path = create_default_config()

    assert config_path == nested_home / ".kanban-tui.yaml"
    assert config_path.exists()


def test_create_default_config_at_explicit_path(tmp_path):
    config_path = tmp_path / "boards" / "personal.yaml"

    created_path = create_default_config(config_path)
    raw = yaml.safe_load(created_path.read_text(encoding="utf-8"))

    assert created_path == config_path.resolve()
    assert raw["data_path"] == str(config_path.resolve().with_suffix(".dat"))
