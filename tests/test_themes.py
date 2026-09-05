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
from kanban_tui.themes import DEFAULT_THEME, get_theme, theme_names
from kanban_tui.tui import KanbanApp


STAMP = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def test_builtin_theme_catalog_is_stable():
    assert DEFAULT_THEME == "arch"
    assert theme_names() == ("arch", "nord", "gruvbox", "dracula", "mono")


def test_theme_lookup_is_case_insensitive():
    assert get_theme("NORD").name == "nord"


def test_unknown_theme_is_rejected():
    with pytest.raises(ValueError, match="unknown theme"):
        get_theme("missing")


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
