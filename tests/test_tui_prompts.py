import click
import pytest
from textual.widgets import Input, Static

from kanban_tui.models import Board
from kanban_tui.services import add_tasks
from kanban_tui.storage import datastore_lock, read_data, write_data
from kanban_tui.transactions import undo_board
from kanban_tui.tui import KanbanApp, MutationPromptScreen


def seed_board(config, *tasks: str) -> None:
    board = Board()
    add_tasks(config, board, tasks)
    with datastore_lock(config):
        write_data(config, board)


@pytest.mark.parametrize(
    "mode,rejected,corrected",
    [
        ("add", "", "new"),
        ("add", "12345", "new"),
        ("edit", "12345", "done"),
        ("tags", "bad tag", "ui"),
    ],
)
async def test_mutation_prompt_rejection_correction_and_success(
    write_config, mode, rejected, corrected
):
    config = write_config(limits={"taskname": 4})
    seed_board(config, "keep")
    original = config.data_path.read_bytes()
    app = KanbanApp(config)

    async with app.run_test(size=(42, 14)) as pilot:
        await pilot.press({"add": "a", "edit": "e", "tags": "t"}[mode])
        screen = app.screen
        assert isinstance(screen, MutationPromptScreen)
        input_widget = screen.query_one(Input)
        input_widget.value = rejected

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is screen
        assert input_widget.value == rejected
        assert input_widget.has_focus
        assert "Error:" in str(screen.query_one("#prompt-status", Static).render())
        assert config.data_path.read_bytes() == original

        input_widget.value = corrected
        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is not screen

    board = read_data(config)
    if mode == "add":
        assert [task.text for task in board.active.values()] == ["keep", "new"]
    elif mode == "edit":
        assert board.active[1].text == "done"
    else:
        assert board.active[1].tags == ("ui",)


async def test_capacity_rejection_then_cancel_preserves_data_and_selection(
    write_config,
):
    config = write_config(limits={"todo": 2})
    seed_board(config, "one", "two")
    original = config.data_path.read_bytes()
    app = KanbanApp(config)

    async with app.run_test(size=(42, 14)) as pilot:
        await pilot.press("j", "a")
        screen = app.screen
        assert isinstance(screen, MutationPromptScreen)
        screen.query_one(Input).value = "three"

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one(Input).value == "three"
        assert "limit reached" in str(
            screen.query_one("#prompt-status", Static).render()
        )
        assert config.data_path.read_bytes() == original

        await pilot.press("escape")
        await pilot.pause()

        assert app.screen is not screen
        assert app._selected_task().id == 2
        assert config.data_path.read_bytes() == original


async def test_lock_error_keeps_add_draft_for_retry(write_config):
    config = write_config()
    seed_board(config, "keep")
    original = config.data_path.read_bytes()
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.press("a")
        screen = app.screen
        assert isinstance(screen, MutationPromptScreen)
        screen.query_one(Input).value = "retry"

        with datastore_lock(config):
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen is screen
            assert screen.query_one(Input).value == "retry"
            assert "locked" in str(screen.query_one("#prompt-status", Static).render())
            assert config.data_path.read_bytes() == original

        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is not screen

    assert [task.text for task in read_data(config).active.values()] == [
        "keep",
        "retry",
    ]
    assert [task.text for task in undo_board(config).active.values()] == ["keep"]


async def test_write_error_keeps_edit_draft_and_writes_once_on_retry(
    write_config, monkeypatch
):
    config = write_config()
    seed_board(config, "before")
    original = config.data_path.read_bytes()
    app = KanbanApp(config)

    import kanban_tui.transactions as transactions

    actual_write = transactions.write_data
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise click.ClickException("simulated write failure")
        return actual_write(*args, **kwargs)

    monkeypatch.setattr(transactions, "write_data", fail_once)

    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        assert isinstance(screen, MutationPromptScreen)
        screen.query_one(Input).value = "after"

        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one(Input).value == "after"
        assert "simulated write failure" in str(
            screen.query_one("#prompt-status", Static).render()
        )
        assert config.data_path.read_bytes() == original

        await pilot.press("enter", "enter")
        await pilot.pause()

        assert app.screen is not screen

    assert calls == 2
    assert read_data(config).active[1].text == "after"
    assert undo_board(config).active[1].text == "before"
