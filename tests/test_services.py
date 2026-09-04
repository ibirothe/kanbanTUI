from pathlib import Path

from kanban_tui.models import AppConfig, Board, Limits, Task, TaskState
from kanban_tui.services import add_tasks, delete_tasks, promote_tasks, regress_tasks


def base_config(**limits):
    return AppConfig(
        clikan_data=Path("/tmp/unused"),
        limits=Limits(**limits),
        repaint=False,
    )


def test_add_and_delete_tasks():
    board = Board()

    add_messages = add_tasks(base_config(), board, ["one", "two"])
    delete_messages = delete_tasks(board, ["1"])

    assert len(board.active) == 1
    assert 1 in board.deleted
    assert board.deleted[1].state is TaskState.DELETED
    assert "Creating new task w/ id: 1 -> one" in add_messages
    assert "Removed task 1." in delete_messages


def test_deleted_highest_id_is_not_reused():
    board = Board()
    config = base_config()
    add_tasks(config, board, ["one", "two"])
    delete_tasks(board, ["2"])

    messages = add_tasks(config, board, ["three"])

    assert 2 in board.deleted
    assert board.deleted[2].text == "two"
    assert 3 in board.active
    assert "Creating new task w/ id: 3 -> three" in messages

    delete_tasks(board, ["3"])
    assert board.deleted[2].text == "two"
    assert board.deleted[3].text == "three"


def test_batch_promotion_respects_wip_limit():
    board = Board()
    config = base_config(wip=1)
    add_tasks(config, board, ["one", "two"])

    messages = promote_tasks(config, board, ["1", "2"])

    assert board.active[1].state is TaskState.IN_PROGRESS
    assert board.active[2].state is TaskState.TODO
    assert "Can not promote, in-progress limit of 1 reached." in messages


def test_regress_done_respects_wip_limit():
    board = Board(
        active={
            1: Task(1, TaskState.IN_PROGRESS, "one", "now", "before"),
            2: Task(2, TaskState.DONE, "two", "now", "before"),
        }
    )
    config = base_config(wip=1)

    messages = regress_tasks(config, board, ["2"])

    assert board.active[2].state is TaskState.DONE
    assert "Can not regress, in-progress limit of 1 reached." in messages


def test_regress_inprogress_returns_to_todo():
    board = Board(
        active={
            1: Task(1, TaskState.IN_PROGRESS, "one", "now", "before")
        }
    )

    messages = regress_tasks(base_config(), board, ["1"])

    assert board.active[1].state is TaskState.TODO
    assert "Regressing task 1 to todo." in messages


def test_regress_inprogress_respects_todo_limit():
    board = Board(
        active={
            1: Task(1, TaskState.TODO, "one", "now", "before"),
            2: Task(2, TaskState.IN_PROGRESS, "two", "now", "before"),
        }
    )
    config = base_config(todo=1)

    messages = regress_tasks(config, board, ["2"])

    assert board.active[2].state is TaskState.IN_PROGRESS
    assert "Can not regress, todo limit of 1 reached." in messages


def test_batch_regression_respects_live_todo_capacity():
    board = Board(
        active={
            1: Task(1, TaskState.IN_PROGRESS, "one", "now", "before"),
            2: Task(2, TaskState.IN_PROGRESS, "two", "now", "before"),
        }
    )
    config = base_config(todo=1)

    messages = regress_tasks(config, board, ["1", "2"])

    assert board.active[1].state is TaskState.TODO
    assert board.active[2].state is TaskState.IN_PROGRESS
    assert "Can not regress, todo limit of 1 reached." in messages
