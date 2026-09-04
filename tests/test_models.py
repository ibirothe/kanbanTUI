import pytest

from kanban_tui.models import Board, Task, TaskState


def test_board_round_trip_preserves_legacy_yaml_shape():
    raw = {
        "data": {1: ["todo", "task", "modified", "created"]},
        "deleted": {2: ["deleted", "old", "modified", "created"]},
    }

    board = Board.from_mapping(raw)

    assert board.active[1] == Task(
        id=1,
        state=TaskState.TODO,
        text="task",
        modified_at="modified",
        created_at="created",
    )
    assert board.deleted[2].state is TaskState.DELETED
    assert board.to_mapping() == raw


def test_invalid_task_state_is_rejected():
    with pytest.raises(ValueError, match="unsupported state"):
        Board.from_mapping(
            {
                "data": {1: ["unknown", "task", "modified", "created"]},
                "deleted": {},
            }
        )


def test_next_task_id_includes_deleted_history():
    board = Board(
        active={1: Task(1, TaskState.TODO, "active", "now", "before")},
        deleted={5: Task(5, TaskState.DELETED, "old", "now", "before")},
    )

    assert board.next_task_id() == 6


def test_active_and_deleted_ids_cannot_overlap():
    raw = {
        "data": {1: ["todo", "active", "now", "before"]},
        "deleted": {1: ["deleted", "old", "now", "before"]},
    }

    with pytest.raises(ValueError, match="both active and deleted: 1"):
        Board.from_mapping(raw)
