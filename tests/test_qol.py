import pytest
from textual.widgets import Input, ListView, Static

from kanban_tui.cli import main
from kanban_tui.models import TaskPriority, TaskState
from kanban_tui.services import add_tasks, delete_tasks
from kanban_tui.storage import read_data
from kanban_tui.tui import ArchiveScreen, KanbanApp
from tests.application_test_support import yaml_application


def test_add_metadata_is_one_atomic_undo(runner, write_config):
    config = write_config()
    result = runner.invoke(
        main,
        [
            "add",
            "--priority",
            "urgent",
            "--tag",
            "Backend",
            "--tag",
            "bug",
            "--tag",
            "backend",
            "Fix",
            "login",
        ],
    )
    assert result.exit_code == 0, result.output
    task = read_data(config).active[1]
    assert task.text == "Fix login"
    assert task.priority is TaskPriority.URGENT
    assert task.tags == ("backend", "bug")
    assert runner.invoke(main, ["undo"]).exit_code == 0
    assert not read_data(config).active


@pytest.mark.parametrize("options", [["--tag", "bad tag"], ["--priority", "invalid"]])
def test_invalid_add_metadata_preserves_data_and_undo(runner, write_config, options):
    config = write_config()
    runner.invoke(main, ["add", "existing"])
    original = config.data_path.read_bytes()
    result = runner.invoke(main, ["add", *options, "invalid"])
    assert result.exit_code != 0
    assert config.data_path.read_bytes() == original


def test_add_option_like_text_after_separator(runner, write_config):
    config = write_config()
    result = runner.invoke(main, ["add", "--", "--priority", "is", "a", "flag"])
    assert result.exit_code == 0
    assert read_data(config).active[1].text == "--priority is a flag"


async def test_refresh_keeps_selection_filter_and_undo(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["keep one", "keep two"])
    )
    app = KanbanApp(config, board_name="work")
    async with app.run_test() as pilot:
        await app._search_prompt_result("keep")
        await pilot.press("j")
        await pilot.pause()
        assert app._selected_task().id == 2
        yaml_application(config).mutate(
            lambda board: add_tasks(config.policy, board, ["keep external"])
        )
        original = config.data_path.read_bytes()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert len(app.board.active) == 3
        assert app._selected_task().id == 2
        assert app.filter_text == "keep"
        assert "work" in app.title
        assert config.data_path.read_bytes() == original


async def test_refresh_error_retains_last_valid_board(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["keep"])
    )
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        config.data_path.write_bytes(b"\xff")
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app._selected_task().text == "keep"
        assert "UTF-8" in str(app.query_one("#status", Static).render())
        assert config.data_path.read_bytes() == b"\xff"


async def test_archive_picker_search_restore_and_undo(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["alpha", "beta"])
    )
    yaml_application(config).mutate(lambda board: delete_tasks(board, ["1", "2"]))
    app = KanbanApp(config)
    async with app.run_test(size=(60, 18)) as pilot:
        await pilot.press("r")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ArchiveScreen)
        screen.query_one(Input).value = "beta"
        await pilot.pause()
        assert len(screen.query_one(ListView).children) == 1
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, ArchiveScreen)
        assert app._selected_task().id == 2
        assert app.board.active[2].state is TaskState.TODO
        await pilot.press("u")
        await pilot.pause()
        assert 2 in app.board.deleted


async def test_archive_picker_rejection_and_cancel_do_not_write(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["archived"])
    )
    yaml_application(config).mutate(lambda board: delete_tasks(board, ["1"]))
    config.limits.todo = 0
    original = config.data_path.read_bytes()
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("r", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ArchiveScreen)
        assert "limit reached" in str(
            app.screen.query_one("#archive-status", Static).render()
        )
        assert config.data_path.read_bytes() == original
        await pilot.press("escape")
        assert not isinstance(app.screen, ArchiveScreen)
        assert config.data_path.read_bytes() == original


async def test_archive_picker_empty_state(write_config):
    app = KanbanApp(write_config())
    async with app.run_test() as pilot:
        await pilot.press("r")
        await pilot.pause()
        assert "No archived tasks" in str(
            app.screen.query_one("#archive-status", Static).render()
        )
        await pilot.press("escape")


async def test_focus_falls_back_after_filter_and_archive(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["alpha", "beta"])
    )
    app = KanbanApp(config, board_name="a-long-board-name-for-a-narrow-terminal")
    async with app.run_test(size=(60, 18)) as pilot:
        await pilot.press("j")
        await app._search_prompt_result("alpha")
        await pilot.pause()
        assert app._selected_task().id == 1
        assert app.board_name in app.title
        await pilot.press("d")
        await pilot.pause()
        assert app._selected_task() is None
        await pilot.press("c")
        await pilot.pause()
        assert app._selected_task().id == 2


async def test_refresh_does_not_create_datastore_or_require_writer_lock(write_config):
    from kanban_tui.storage import datastore_lock

    config = write_config()
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+r")
        assert not config.data_path.exists()
        yaml_application(config).mutate(
            lambda board: add_tasks(config.policy, board, ["external"])
        )
        with datastore_lock(config):
            await pilot.press("ctrl+r")
            await pilot.pause()
        assert app._selected_task().text == "external"


@pytest.mark.parametrize(
    "selection,identity",
    [
        ([], "default"),
        (["--board", "work"], "work"),
        (["--config", "custom.yaml"], "config: custom.yaml"),
    ],
)
def test_cli_passes_board_identity(
    runner, write_config, monkeypatch, tmp_path, selection, identity
):
    write_config()
    if selection[:1] == ["--config"]:
        selection = ["--config", str(tmp_path / "custom.yaml")]
    if selection[:1] == ["--board"]:
        runner.invoke(main, ["board", "create", "work"])
    elif selection[:1] == ["--config"]:
        runner.invoke(main, [*selection, "configure"])
    captured = []
    monkeypatch.setattr(
        "kanban_tui.tui.run_tui",
        lambda config, *, application, board_name: captured.append(board_name),
    )
    result = runner.invoke(main, [*selection, "tui"])
    assert result.exit_code == 0, result.output
    assert captured == [identity]
