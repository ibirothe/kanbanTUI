from datetime import datetime, timezone
from pathlib import Path

from kanban_tui.models import AppConfig, Board, Limits, Task, TaskState
from kanban_tui.services import (
    add_tasks,
    delete_tasks,
    edit_task,
    promote_tasks,
    regress_tasks,
    restore_tasks,
)


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def base_config(**limits):
    return AppConfig(
        clikan_data=Path("/tmp/unused"),
        limits=Limits(**limits),
        repaint=False,
    )


def task(task_id, state, text):
    return Task(task_id, state, text, NOW, BEFORE)


def test_add_and_delete_tasks():
    board = Board()

    add_result = add_tasks(base_config(), board, ["one", "two"])
    delete_result = delete_tasks(board, ["1"])

    assert len(board.active) == 1
    assert 1 in board.deleted
    assert board.deleted[1].state is TaskState.DELETED
    assert add_result.succeeded == 2
    assert add_result.failed == 0
    assert "Creating new task w/ id: 1 -> one" in add_result.messages
    assert "Removed task 1." in delete_result.messages


def test_add_normalizes_outer_whitespace_and_rejects_empty_text():
    board = Board()

    result = add_tasks(base_config(), board, ["  one  ", "   "])

    assert board.active[1].text == "one"
    assert result.succeeded == 1
    assert result.failed == 1
    assert "Task text cannot be empty." in result.messages


def test_deleted_highest_id_is_not_reused():
    board = Board()
    config = base_config()
    add_tasks(config, board, ["one", "two"])
    delete_tasks(board, ["2"])

    result = add_tasks(config, board, ["three"])

    assert 2 in board.deleted
    assert board.deleted[2].text == "two"
    assert 3 in board.active
    assert "Creating new task w/ id: 3 -> three" in result.messages

    delete_tasks(board, ["3"])
    assert board.deleted[2].text == "two"
    assert board.deleted[3].text == "three"


def test_edit_updates_text_without_changing_task_identity_or_state():
    original = task(1, TaskState.IN_PROGRESS, "old")
    board = Board(active={1: original})

    result = edit_task(base_config(), board, "1", "  new task text  ")

    assert result.succeeded == 1
    assert board.active[1].id == 1
    assert board.active[1].state is TaskState.IN_PROGRESS
    assert board.active[1].text == "new task text"
    assert board.active[1].created_at == BEFORE
    assert board.active[1].modified_at != NOW
    assert board.active[1].modified_at.tzinfo is not None


def test_edit_deleted_task_is_rejected():
    board = Board(deleted={1: task(1, TaskState.DELETED, "old")})

    result = edit_task(base_config(), board, "1", "new")

    assert result.failed == 1
    assert "Can not edit deleted task 1." in result.messages


def test_restore_preserves_id_and_creation_time():
    board = Board(deleted={1: task(1, TaskState.DELETED, "old")})

    result = restore_tasks(base_config(), board, ["1"])

    assert result.succeeded == 1
    assert 1 not in board.deleted
    assert board.active[1].id == 1
    assert board.active[1].state is TaskState.TODO
    assert board.active[1].created_at == BEFORE
    assert board.active[1].modified_at != NOW
    assert board.active[1].modified_at.tzinfo is not None


def test_restore_respects_todo_limit():
    board = Board(
        active={1: task(1, TaskState.TODO, "active")},
        deleted={2: task(2, TaskState.DELETED, "old")},
    )

    result = restore_tasks(base_config(todo=1), board, ["2"])

    assert result.failed == 1
    assert 2 in board.deleted
    assert "Can not restore, todo limit of 1 reached." in result.messages


def test_batch_promotion_respects_wip_limit():
    board = Board()
    config = base_config(wip=1)
    add_tasks(config, board, ["one", "two"])

    result = promote_tasks(config, board, ["1", "2"])

    assert board.active[1].state is TaskState.IN_PROGRESS
    assert board.active[2].state is TaskState.TODO
    assert result.succeeded == 1
    assert result.failed == 1
    assert "Can not promote, in-progress limit of 1 reached." in result.messages


def test_regress_done_respects_wip_limit():
    board = Board(
        active={
            1: task(1, TaskState.IN_PROGRESS, "one"),
            2: task(2, TaskState.DONE, "two"),
        }
    )
    config = base_config(wip=1)

    result = regress_tasks(config, board, ["2"])

    assert board.active[2].state is TaskState.DONE
    assert result.failed == 1
    assert "Can not regress, in-progress limit of 1 reached." in result.messages


def test_regress_inprogress_returns_to_todo():
    board = Board(active={1: task(1, TaskState.IN_PROGRESS, "one")})

    result = regress_tasks(base_config(), board, ["1"])

    assert board.active[1].state is TaskState.TODO
    assert result.succeeded == 1
    assert "Regressing task 1 to todo." in result.messages


def test_regress_inprogress_respects_todo_limit():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "one"),
            2: task(2, TaskState.IN_PROGRESS, "two"),
        }
    )
    config = base_config(todo=1)

    result = regress_tasks(config, board, ["2"])

    assert board.active[2].state is TaskState.IN_PROGRESS
    assert result.failed == 1
    assert "Can not regress, todo limit of 1 reached." in result.messages


def test_batch_regression_respects_live_todo_capacity():
    board = Board(
        active={
            1: task(1, TaskState.IN_PROGRESS, "one"),
            2: task(2, TaskState.IN_PROGRESS, "two"),
        }
    )
    config = base_config(todo=1)

    result = regress_tasks(config, board, ["1", "2"])

    assert board.active[1].state is TaskState.TODO
    assert board.active[2].state is TaskState.IN_PROGRESS
    assert result.succeeded == 1
    assert result.failed == 1
    assert "Can not regress, todo limit of 1 reached." in result.messages
