import json
from datetime import datetime, timezone
from pathlib import Path

from kanban_tui.models import AppConfig, Board, Limits, Task, TaskState
from kanban_tui.rendering import (
    board_columns,
    format_json,
    format_plain,
    split_items,
)


def stamp(hour: int):
    return datetime(2026, 9, 4, hour, 0, tzinfo=timezone.utc)


def config(*, done_limit: int = 10):
    return AppConfig(
        data_path=Path("/tmp/unused"),
        limits=Limits(done=done_limit),
    )


def task(
    task_id: int,
    state: TaskState,
    text: str,
    hour: int,
    *,
    position: int = 0,
):
    return Task(task_id, state, text, stamp(hour), stamp(8), position=position)


def done(task_id: int, text: str, hour: int):
    return task(task_id, TaskState.DONE, text, hour)


def test_active_tasks_are_sorted_by_manual_position():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "second", 9, position=2),
            2: task(2, TaskState.TODO, "first", 9, position=1),
            3: task(3, TaskState.IN_PROGRESS, "doing second", 9, position=2),
            4: task(4, TaskState.IN_PROGRESS, "doing first", 9, position=1),
        }
    )

    todos, inprogs, _ = split_items(board)

    assert todos == ["[2] first", "[1] second"]
    assert inprogs == ["[4] doing first", "[3] doing second"]


def test_done_tasks_are_sorted_by_modified_time_newest_first():
    board = Board(
        active={
            1: done(1, "oldest", 9),
            2: done(2, "newest", 12),
            3: done(3, "middle", 10),
        }
    )

    _, _, dones = split_items(board)

    assert dones == ["[2] newest", "[3] middle", "[1] oldest"]


def test_done_limit_selects_newest_completed_tasks():
    board = Board(
        active={
            1: done(1, "oldest", 9),
            2: done(2, "newest", 12),
            3: done(3, "middle", 10),
        }
    )

    _, _, dones = board_columns(config(done_limit=2), board)

    assert dones == ["[2] newest", "[3] middle"]


def test_json_output_is_structured_and_deterministic():
    board = Board(
        active={
            3: task(3, TaskState.TODO, "todo three", 9, position=2),
            1: task(1, TaskState.TODO, "todo one", 9, position=1),
            4: task(4, TaskState.IN_PROGRESS, "doing", 10),
            2: done(2, "done", 12),
        }
    )

    payload = json.loads(format_json(config(), board))

    assert [item["id"] for item in payload["tasks"]] == [1, 3, 4, 2]
    assert payload["tasks"][0] == {
        "id": 1,
        "state": "todo",
        "text": "todo one",
        "created_at": "2026-09-04T08:00:00+00:00",
        "modified_at": "2026-09-04T09:00:00+00:00",
    }


def test_plain_output_is_stable_color_free_and_escapes_control_text():
    board = Board(
        active={
            1: task(1, TaskState.TODO, "line\tbreak\nnext", 9),
        }
    )

    output = format_plain(config(), board)

    assert output.splitlines()[0] == "id\tstate\ttext\tcreated_at\tmodified_at"
    assert "1\ttodo\tline\\tbreak\\nnext\t" in output
    assert "\x1b[" not in output
