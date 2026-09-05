from datetime import datetime, timezone
from pathlib import Path

import click
import pytest
import yaml
from textual.widgets import Static

from kanban_tui.cli import main
from kanban_tui.config import get_board_config_path, get_config_path, validate_config
from kanban_tui.models import AppConfig, Board, Task, TaskPriority, TaskState
from kanban_tui.rendering import render_board, task_rich_text
from kanban_tui.themes import (
    DEFAULT_THEME,
    get_theme,
    get_user_theme_dir,
    theme_names,
)
from kanban_tui.tui import KanbanApp


STAMP = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def write_user_theme(name: str, payload: dict) -> Path:
    theme_dir = get_user_theme_dir()
    theme_dir.mkdir(parents=True, exist_ok=True)
    path = theme_dir / f"{name}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_builtin_theme_catalog_is_stable():
    assert DEFAULT_THEME == "arch"
    assert theme_names() == ("arch", "nord", "gruvbox", "dracula", "mono")


def test_theme_lookup_is_case_insensitive():
    assert get_theme("NORD").name == "nord"


def test_unknown_theme_is_rejected():
    with pytest.raises(ValueError, match="unknown theme"):
        get_theme("missing")


def test_custom_theme_is_discovered_and_inherits_builtin_palette():
    write_user_theme(
        "ocean",
        {
            "description": "Ocean development theme",
            "extends": "nord",
            "colors": {
                "accent": "#123456",
                "todo": "#abcdef",
            },
        },
    )

    theme = get_theme("ocean")
    nord = get_theme("nord")

    assert "ocean" in theme_names()
    assert theme.name == "ocean"
    assert theme.source == "custom"
    assert theme.description == "Ocean development theme"
    assert theme.accent == "#123456"
    assert theme.todo == "#abcdef"
    assert theme.background == nord.background
    assert theme.priority_urgent == nord.priority_urgent


def test_custom_theme_defaults_to_arch_when_extends_is_omitted():
    write_user_theme("minimal", {"colors": {"done": "#010203"}})

    theme = get_theme("minimal")

    assert theme.done == "#010203"
    assert theme.background == get_theme("arch").background
    assert theme.description == "Custom theme based on arch"


def test_custom_theme_path_uses_portable_home(isolated_app_home):
    assert get_user_theme_dir() == isolated_app_home / "themes"


def test_custom_theme_path_uses_xdg_config_home(monkeypatch, tmp_path):
    xdg_config = tmp_path / "xdg-config"
    monkeypatch.delenv("KANBAN_TUI_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    assert get_user_theme_dir() == (xdg_config / "kanban-tui" / "themes").resolve()


def test_builtin_theme_name_cannot_be_overridden():
    write_user_theme("arch", {"colors": {"accent": "#ffffff"}})

    with pytest.raises(ValueError, match="reserved built-in name"):
        tuple(theme_names())


def test_custom_theme_rejects_invalid_color_and_unknown_role():
    write_user_theme("bad-color", {"colors": {"accent": "blue"}})
    with pytest.raises(ValueError, match=r"colors\.accent must be a #RRGGBB color"):
        get_theme("bad-color")

    (get_user_theme_dir() / "bad-color.yaml").unlink()
    write_user_theme("bad-role", {"colors": {"sidebar": "#112233"}})
    with pytest.raises(ValueError, match="unknown color roles"):
        get_theme("bad-role")


def test_custom_theme_rejects_non_builtin_parent():
    write_user_theme("child", {"extends": "another-custom"})

    with pytest.raises(ValueError, match="extends must be one of the built-in themes"):
        get_theme("child")


def test_config_without_theme_defaults_to_arch(tmp_path):
    config = validate_config(
        {"data_path": str(tmp_path / "board.dat")},
        tmp_path / "config.yaml",
    )

    assert config.theme == "arch"


def test_invalid_config_theme_is_rejected(tmp_path):
    with pytest.raises(click.ClickException, match="unknown theme"):
        validate_config(
            {"data_path": str(tmp_path / "board.dat"), "theme": "missing"},
            tmp_path / "config.yaml",
        )


def test_custom_theme_is_valid_in_config(tmp_path):
    write_user_theme("ocean", {"extends": "gruvbox", "colors": {"accent": "#112233"}})

    config = validate_config(
        {"data_path": str(tmp_path / "board.dat"), "theme": "ocean"},
        tmp_path / "config.yaml",
    )

    assert config.theme == "ocean"


def test_theme_cli_lists_sets_and_reports_selected_theme(runner, write_config):
    write_config()

    current = runner.invoke(main, ["theme", "current"])
    listing = runner.invoke(main, ["theme", "list"])
    changed = runner.invoke(main, ["theme", "set", "nord"])
    config_show = runner.invoke(main, ["config", "show"])

    assert current.exit_code == 0
    assert current.output == "arch\n"
    assert listing.exit_code == 0
    assert "* arch\t" in listing.output
    assert "  nord\t" in listing.output
    assert changed.exit_code == 0
    assert "Theme set to nord" in changed.output
    assert "theme: nord" in config_show.output


def test_theme_cli_discovers_custom_theme_created_after_cli_import(runner, write_config):
    write_config()
    write_user_theme(
        "ocean",
        {
            "description": "Ocean development theme",
            "extends": "arch",
            "colors": {"accent": "#00aaff"},
        },
    )

    listing = runner.invoke(main, ["theme", "list"])
    changed = runner.invoke(main, ["theme", "set", "ocean"])

    assert listing.exit_code == 0
    assert "ocean\tOcean development theme" in listing.output
    assert changed.exit_code == 0
    assert "Theme set to ocean" in changed.output
    assert yaml.safe_load(get_config_path().read_text(encoding="utf-8"))["theme"] == "ocean"


def test_invalid_custom_theme_cli_error_is_actionable(runner, write_config):
    write_config()
    write_user_theme("bad", {"colors": {"accent": "not-a-color"}})

    result = runner.invoke(main, ["theme", "set", "bad"])

    assert result.exit_code != 0
    assert "#RRGGBB" in result.output


def test_config_set_theme_uses_same_validation(runner, write_config):
    write_config()

    changed = runner.invoke(main, ["config", "set", "theme", "gruvbox"])
    invalid = runner.invoke(main, ["config", "set", "theme", "missing"])

    assert changed.exit_code == 0
    raw = yaml.safe_load(get_config_path().read_text(encoding="utf-8"))
    assert raw["theme"] == "gruvbox"
    assert invalid.exit_code != 0
    assert "unknown theme" in invalid.output


def test_named_boards_keep_independent_theme_selection(runner):
    assert runner.invoke(main, ["board", "create", "work"]).exit_code == 0
    assert runner.invoke(main, ["board", "create", "personal"]).exit_code == 0

    changed = runner.invoke(main, ["--board", "work", "theme", "set", "dracula"])

    assert changed.exit_code == 0
    work = yaml.safe_load(get_board_config_path("work").read_text(encoding="utf-8"))
    personal = yaml.safe_load(
        get_board_config_path("personal").read_text(encoding="utf-8")
    )
    assert work["theme"] == "dracula"
    assert personal["theme"] == "arch"


def test_named_board_can_select_custom_theme(runner):
    write_user_theme("ocean", {"colors": {"accent": "#00aaff"}})
    assert runner.invoke(main, ["board", "create", "work"]).exit_code == 0

    changed = runner.invoke(main, ["--board", "work", "theme", "set", "ocean"])

    assert changed.exit_code == 0
    work = yaml.safe_load(get_board_config_path("work").read_text(encoding="utf-8"))
    assert work["theme"] == "ocean"


def test_rich_task_text_uses_theme_semantic_styles():
    task = Task(
        1,
        TaskState.TODO,
        "Fix login",
        STAMP,
        STAMP,
        priority=TaskPriority.URGENT,
        tags=("backend",),
    )
    theme = get_theme("nord")

    rendered = task_rich_text(task, theme)
    styles = [str(span.style) for span in rendered.spans]

    assert rendered.plain == "[1] !urgent Fix login #backend"
    assert any(theme.priority_urgent in style for style in styles)
    assert any(theme.accent in style for style in styles)


def test_no_color_disables_rich_ansi(monkeypatch, capsys):
    config = AppConfig(data_path=Path("/tmp/unused"), theme="dracula")
    board = Board(
        active={
            1: Task(
                1,
                TaskState.TODO,
                "Fix login",
                STAMP,
                STAMP,
                priority=TaskPriority.URGENT,
                tags=("backend",),
            )
        }
    )
    monkeypatch.setenv("NO_COLOR", "1")

    render_board(config, board, "test")
    output = capsys.readouterr().out

    assert "Fix login" in output
    assert "\x1b[" not in output


async def test_tui_applies_selected_palette(write_config):
    config = write_config()
    config.theme = "gruvbox"
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.palette.name == "gruvbox"
        assert app.query_one("#todo-title", Static).styles.color is not None
        assert app.query_one("#status", Static).styles.background is not None


async def test_tui_applies_custom_palette(write_config):
    write_user_theme(
        "ocean",
        {
            "extends": "arch",
            "colors": {
                "accent": "#00aaff",
                "todo": "#11bbff",
            },
        },
    )
    config = write_config()
    config.theme = "ocean"
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.palette.name == "ocean"
        assert app.palette.source == "custom"
        assert app.palette.accent == "#00aaff"
