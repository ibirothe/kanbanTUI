import pytest
import yaml

from kanban_tui.cli import main
from kanban_tui.config import get_config_path
from kanban_tui.themes import get_user_theme_dir, theme_names


def test_custom_theme_filename_must_be_lowercase_slug():
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "Ocean Blue.yaml").write_text(
        yaml.safe_dump({"colors": {"accent": "#00aaff"}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="lowercase theme slug"):
        tuple(theme_names())


def test_invalid_unused_custom_theme_does_not_block_switch_to_builtin(
    runner, write_config
):
    write_config()
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "broken.yaml").write_text(
        yaml.safe_dump({"colors": {"accent": "not-a-color"}}),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["theme", "set", "arch"])

    assert result.exit_code == 0
    assert yaml.safe_load(get_config_path().read_text(encoding="utf-8"))["theme"] == "arch"


def test_theme_list_reports_invalid_custom_theme_cleanly(runner, write_config):
    write_config()
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True, exist_ok=True)
    (theme_dir / "broken.yaml").write_text(
        yaml.safe_dump({"colors": {"accent": "not-a-color"}}),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["theme", "list"])

    assert result.exit_code != 0
    assert "#RRGGBB" in result.output
