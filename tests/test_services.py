from datetime import datetime, timezone

from kanban_tui.models import Board, Task, TaskState
from kanban_tui.policy import BoardPolicy
from kanban_tui.results import OperationCode, OperationStatus
from kanban_tui.services import (
    add_tasks,
    delete_tasks,
    edit_task,
    move_tasks_to_state,
    promote_tasks,
    regress_tasks,
    reorder_task,
    restore_tasks,
)

NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
BEFORE = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def base_config(**limits) -> BoardPolicy:
    return BoardPolicy(
        todo_limit=limits.get("todo"),
        wip_limit=limits.get("wip"),
    )


def task(task_id, state, text, position=0):
    return Task(task_id, state, text, NOW, BEFORE, position=position)


def codes(result):
    return [item.code for item in result.items]


def test_add_and_delete_tasks():
    board = Board()

    add_result = add_tasks(base_config(), board, ["one", "two"])
    delete_result = delete_tasks(board, ["1"])

    assert len(board.active) == 1
    assert 1 in board.deleted
    assert board.deleted[1].state is TaskState.DELETED
    assert board.active[2].position == 1
    assert add_result.succeeded == 2
    assert add_result.failed == 0
    assert codes(add_result) == [OperationCode.TASK_ADDED, OperationCode.TASK_ADDED]
    assert codes(delete_result) == [OperationCode.TASK_ARCHIVED]


def test_add_normalizes_outer_whitespace_and_rejects_empty_text():
    board = Board()

    result = add_tasks(base_config(), board, ["  one  ", "   "])

    assert board.active[1].text == "one"
    assert result.succeeded == 1
    assert result.failed == 1
    assert codes(result) == [OperationCode.TASK_ADDED, OperationCode.TEXT_EMPTY]
    assert result.items[1].status is OperationStatus.REJECTED


def test_deleted_highest_id_is_not_reused():
    board = Board()
    config = base_config()
    add_tasks(config, board, ["one", "two"])
    delete_tasks(board, ["2"])

    result = add_tasks(config, board, ["three"])

    assert 2 in board.deleted
    assert board.deleted[2].text == "two"
    assert 3 in board.active
    assert len(result.items) == 1
    assert result.items[0].code is OperationCode.TASK_ADDED
    assert (result.items[0].task_id, result.items[0].text) == (3, "three")

    delete_tasks(board, ["3"])
    assert board.deleted[2].text == "two"
    assert board.deleted[3].text == "three"


def test_edit_updates_text_without_changing_task_identity_state_or_position():
    original = task(1, TaskState.IN_PROGRESS, "old", position=4)
    board = Board(active={1: original})

    result = edit_task(base_config(), board, "1", "  new task text  ")

    assert result.succeeded == 1
    assert board.active[1].id == 1
    assert board.active[1].state is TaskState.IN_PROGRESS
    assert board.active[1].text == "new task text"
    assert board.active[1].position == 4
    assert board.active[1].created_at == BEFORE
    assert board.active[1].modified_at != NOW
    assert board.active[1].modified_at.tzinfo is not None
    assert codes(result) == [OperationCode.TASK_UPDATED]
    assert (result.items[0].task_id, result.items[0].text) == (1, "new task text")


def test_edit_with_normalized_identical_text_is_unchanged(monkeypatch):
    original = task(1, TaskState.IN_PROGRESS, "same", position=4)
    board = Board(active={1: original})

    def unexpected_timestamp():
        raise AssertionError("unchanged edit must not request a timestamp")

    monkeypatch.setattr("kanban_tui.services.timestamp", unexpected_timestamp)

    result = edit_task(base_config(), board, "1", "  same  ")

    assert result.ok
    assert result.succeeded == 1
    assert codes(result) == [OperationCode.TASK_UNCHANGED]
    assert result.items[0].status is OperationStatus.UNCHANGED
    assert board.active[1] is original
    assert original.modified_at == NOW


def test_edit_deleted_task_is_rejected():
    board = Board(deleted={1: task(1, TaskState.DELETED, "old")})

    result = edit_task(base_config(), board, "1", "new")

    assert result.failed == 1
    assert codes(result) == [OperationCode.ARCHIVED_TASK_NOT_EDITABLE]
    assert result.items[0].task_id == 1


def test_restore_preserves_id_creation_time_and_moves_to_bottom():
    board = Board(
        active={2: task(2, TaskState.TODO, "active", position=1)},
        deleted={1: task(1, TaskState.DELETED, "old", position=9)},
    )

    result = restore_tasks(base_config(), board, ["1"])

    assert result.succeeded == 1
    assert 1 not in board.deleted
    assert board.active[1].id == 1
    assert board.active[1].state is TaskState.TODO
    assert board.active[1].position == 2
    assert board.active[1].created_at == BEFORE
    assert board.active[1].modified_at != NOW
    assert board.active[1].modified_at.tzinfo is not None
    assert codes(result) == [OperationCode.TASK_RESTORED]


def test_restore_respects_todo_limit():
    board = Board(
        active={1: task(1, TaskState.TODO, "active")},
        deleted={2: task(2, TaskState.DELETED, "old")},
    )

    result = restore_tasks(base_config(todo=1), board, ["2"])

    assert result.failed == 1
    assert 2 in board.deleted
    assert codes(result) == [OperationCode.STATE_LIMIT_REACHED]
    assert (result.items[0].state, result.items[0].count, result.items[0].limit) == (
        TaskState.TODO,
        1,
        1,
    )


def test_explicit_state_commands_move_directly_to_target_state():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "one", position=1),
            2: task(2, TaskState.DONE, "two", position=2),
        }
    )
    config = base_config()

    start_result = move_tasks_to_state(config, board, ["1"], TaskState.IN_PROGRESS)
    todo_result = move_tasks_to_state(config, board, ["2"], TaskState.TODO)
    done_result = move_tasks_to_state(config, board, ["1"], TaskState.DONE)

    assert codes(start_result) == [OperationCode.TASK_STARTED]
    assert codes(todo_result) == [OperationCode.TASK_MOVED]
    assert todo_result.items[0].state is TaskState.TODO
    assert codes(done_result) == [OperationCode.TASK_COMPLETED]
    assert board.active[1].state is TaskState.DONE
    assert board.active[2].state is TaskState.TODO


def test_explicit_state_command_rejects_same_state_and_capacity():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "one", position=1),
            2: task(2, TaskState.TODO, "two", position=2),
        }
    )

    same = move_tasks_to_state(base_config(), board, ["1"], TaskState.TODO)
    full = move_tasks_to_state(base_config(wip=0), board, ["1"], TaskState.IN_PROGRESS)

    assert codes(same) == [OperationCode.TASK_ALREADY_IN_STATE]
    assert same.items[0].status is OperationStatus.UNCHANGED
    assert codes(full) == [OperationCode.STATE_LIMIT_REACHED]


def test_batch_promotion_respects_wip_limit():
    board = Board()
    config = base_config(wip=1)
    add_tasks(config, board, ["one", "two"])

    result = promote_tasks(config, board, ["1", "2"])

    assert board.active[1].state is TaskState.IN_PROGRESS
    assert board.active[1].position == 1
    assert board.active[2].state is TaskState.TODO
    assert board.active[2].position == 1
    assert result.succeeded == 1
    assert result.failed == 1
    assert codes(result) == [
        OperationCode.TASK_STARTED,
        OperationCode.STATE_LIMIT_REACHED,
    ]
    assert [item.task_id for item in result.items] == [1, 2]
    assert [item.status for item in result.items] == [
        OperationStatus.CHANGED,
        OperationStatus.REJECTED,
    ]


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
    assert codes(result) == [OperationCode.STATE_LIMIT_REACHED]


def test_regress_inprogress_returns_to_todo_at_bottom():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "existing", position=1),
            2: task(2, TaskState.IN_PROGRESS, "moving", position=1),
        }
    )

    result = regress_tasks(base_config(), board, ["2"])

    assert board.active[2].state is TaskState.TODO
    assert board.active[2].position == 2
    assert result.succeeded == 1
    assert codes(result) == [OperationCode.TASK_MOVED]
    assert result.items[0].state is TaskState.TODO


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
    assert codes(result) == [OperationCode.STATE_LIMIT_REACHED]


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
    assert codes(result) == [
        OperationCode.TASK_MOVED,
        OperationCode.STATE_LIMIT_REACHED,
    ]


def test_reorder_task_supports_top_bottom_before_and_after():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "one", position=1),
            2: task(2, TaskState.TODO, "two", position=2),
            3: task(3, TaskState.TODO, "three", position=3),
        }
    )

    assert reorder_task(board, "3", "top").ok
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [3, 1, 2]

    assert reorder_task(board, "3", "bottom").ok
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [1, 2, 3]

    assert reorder_task(board, "3", "before", "2").ok
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [1, 3, 2]

    assert reorder_task(board, "1", "after", "3").ok
    assert [task.id for task in board.ordered_tasks(TaskState.TODO)] == [3, 1, 2]


def test_reorder_rejects_cross_column_reference_and_done_tasks():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "todo", position=1),
            2: task(2, TaskState.IN_PROGRESS, "doing", position=1),
            3: task(3, TaskState.DONE, "done", position=1),
        }
    )

    cross_column = reorder_task(board, "1", "before", "2")
    done = reorder_task(board, "3", "top")

    assert cross_column.failed == 1
    assert codes(cross_column) == [OperationCode.REFERENCE_DIFFERENT_STATE]
    assert done.failed == 1
    assert codes(done) == [OperationCode.DONE_ORDER_FIXED]
