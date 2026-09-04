import click
import pytest
import yaml

from kanban_tui.config import get_config_path, read_config, validate_config


def test_config_defaults_are_normalized(tmp_path):
    config = validate_config(
        {"clikan_data": str(tmp_path / ".clikan.dat")},
        tmp_path / ".clikan.yaml",
    )

    assert config.limits.taskname == 40
    assert config.limits.done == 10
    assert config.repaint is False


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
