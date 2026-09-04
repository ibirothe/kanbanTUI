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
    try:
        Board.from_mapping(
            {
                "data": {1: ["unknown", "task", "modified", "created"]},
                "deleted": {},
            }
        )
    except ValueError as exc:
        assert "unsupported state" in str(exc)
    else:
        raise AssertionError("invalid task state was accepted")
