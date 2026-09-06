from datetime import datetime, timezone

import pytest
from textual.widgets import Input, Static

from kanban_tui.models import TaskPriority, TaskState
from kanban_tui.services import (
    OperationResult,
    add_tasks,
    delete_tasks,
    edit_task,
    move_tasks_to_state,
    reorder_task,
    set_task_priority,
    set_task_tags,
)
from kanban_tui.storage import read_data
from kanban_tui.transactions import mutate_board, undo_board
from kanban_tui.tui import ArchiveScreen, KanbanApp, PromptScreen


@pytest.mark.parametrize("key", ["e", "t"])
async def test_conflicting_prompt_preserves_draft_and_requires_review(
    write_config, monkeypatch, key
):
    config = write_config()
    monkeypatch.setattr(
        "kanban_tui.services.timestamp",
        lambda: datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
    )
    mutate_board(config, lambda b: add_tasks(config, b, ["original"]))
    app = KanbanApp(config)
    async with app.run_test(size=(60, 24)) as pilot:
        await pilot.press(key)
        screen = app.screen
        screen.query_one(Input).value = "draft"

        def external(board):
            if key == "e":
                return edit_task(config, board, "1", "external")
            return set_task_tags(board, "1", ["external"])

        mutate_board(config, external)
        original = config.data_path.read_bytes()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is screen
        assert screen.query_one(Input).value == "draft"
        assert "Conflict" in str(screen.query_one("#prompt-status", Static).render())
        assert config.data_path.read_bytes() == original
        await pilot.press("enter")
        assert config.data_path.read_bytes() == original
        await pilot.press("ctrl+r")
        assert screen.query_one(Input).value == "draft"
        assert "external" in str(screen.query_one("#prompt-status", Static).render())
        assert config.data_path.read_bytes() == original
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, PromptScreen)
    task = read_data(config).active[1]
    assert (task.text if key == "e" else task.tags) == (
        "draft" if key == "e" else ("draft",)
    )
    previous = undo_board(config).active[1]
    assert (previous.text if key == "e" else previous.tags) == (
        "external" if key == "e" else ("external",)
    )


@pytest.mark.parametrize("external_action", ["archive", "replace", "remove"])
async def test_prompt_rejects_changed_task_identity(write_config, external_action):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["original"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        screen.query_one(Input).value = "draft"

        def external(board):
            if external_action == "archive":
                return delete_tasks(board, ["1"])
            board.active.clear()
            if external_action == "replace":
                # Replace import may reuse a numeric ID for a different task.
                return add_tasks(config, board, ["replacement"])
            return OperationResult(succeeded=1)

        mutate_board(config, external)
        original = config.data_path.read_bytes()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is screen
        assert screen.query_one(Input).value == "draft"
        assert config.data_path.read_bytes() == original
        if external_action != "replace":
            await pilot.press("ctrl+r", "enter")
            assert app.screen is screen
            assert screen.query_one(Input).value == "draft"
            assert config.data_path.read_bytes() == original
        await pilot.press("escape")
        assert config.data_path.read_bytes() == original


async def test_review_is_rechecked_before_commit(write_config):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["one"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("e")
        screen = app.screen
        screen.query_one(Input).value = "draft"
        mutate_board(config, lambda b: edit_task(config, b, "1", "external one"))
        await pilot.press("enter", "ctrl+r")
        mutate_board(config, lambda b: edit_task(config, b, "1", "external two"))
        original = config.data_path.read_bytes()
        await pilot.press("enter")
        assert app.screen is screen
        assert screen.query_one(Input).value == "draft"
        assert "Conflict" in str(screen.query_one("#prompt-status", Static).render())
        assert config.data_path.read_bytes() == original


async def test_relative_reorder_uses_current_neighbor(write_config):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["one", "two", "three"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("j")

        def external(board):
            # A replace/import can change the neighbors while task #2 is unchanged.
            board.active[1].position, board.active[3].position = 3, 1
            return OperationResult(succeeded=1)

        mutate_board(config, external)
        await pilot.press("shift+up")
        await pilot.pause()
        assert [t.id for t in read_data(config).ordered_tasks(TaskState.TODO)] == [
            2,
            3,
            1,
        ]


async def test_prompt_allows_unrelated_task_change(write_config):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["one", "two"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("e")
        app.screen.query_one(Input).value = "edited one"
        mutate_board(config, lambda b: edit_task(config, b, "2", "external two"))
        await pilot.press("enter")
        await pilot.pause()
        assert not isinstance(app.screen, PromptScreen)
    assert [t.text for t in read_data(config).active.values()] == [
        "edited one",
        "external two",
    ]


async def test_unchanged_edit_prompt_closes_without_replacing_undo(write_config):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["same"]))
    original = config.data_path.read_bytes()
    app = KanbanApp(config)

    async with app.run_test() as pilot:
        await pilot.press("e")
        app.screen.query_one(Input).value = "  same  "
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, PromptScreen)
        assert "Task #1 is unchanged." in str(app.query_one("#status", Static).render())

    assert config.data_path.read_bytes() == original
    assert not undo_board(config).active


@pytest.mark.parametrize("key", ["p", "right", "d", "shift+up"])
async def test_stale_shortcuts_reject_then_refresh(write_config, key):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["one", "two", "three"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("j")
        assert app._selected_task().id == 2

        def external(board):
            if key == "p":
                return set_task_priority(board, "2", TaskPriority.HIGH)
            if key == "right":
                return move_tasks_to_state(config, board, ["2"], TaskState.DONE)
            if key == "shift+up":
                return reorder_task(board, "2", "bottom")
            return edit_task(config, board, "2", "external")

        mutate_board(config, external)
        original = config.data_path.read_bytes()
        await pilot.press(key)
        await pilot.pause()
        assert config.data_path.read_bytes() == original
        assert "Conflict" in str(app.query_one("#status", Static).render())
        assert app.board == read_data(config)


async def test_archive_picker_rejects_replaced_entry(write_config):
    config = write_config()
    mutate_board(config, lambda b: add_tasks(config, b, ["one"]))
    mutate_board(config, lambda b: delete_tasks(b, ["1"]))
    app = KanbanApp(config)
    async with app.run_test() as pilot:
        await pilot.press("r")
        assert isinstance(app.screen, ArchiveScreen)

        def external(board):
            board.deleted[1].text = "replaced archive"
            return OperationResult(succeeded=1)

        mutate_board(config, external)
        original = config.data_path.read_bytes()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ArchiveScreen)
        assert "Conflict" in str(
            app.screen.query_one("#archive-status", Static).render()
        )
        assert config.data_path.read_bytes() == original
