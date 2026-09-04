from datetime import datetime, timezone
from pathlib import Path

from kanban_tui.models import AppConfig, Board, Limits, Task, TaskState
from kanban_tui.rendering import board_columns, split_items


def stamp(hour: int):
    return datetime(2026, 9, 4, hour, 0, tzinfo=timezone.utc)


def done(task_id: int, text: str, hour: int):
    return Task(
        task_id,
        TaskState.DONE,
        text,
        stamp(hour),
        stamp(8),
    )


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
    config = AppConfig(
        clikan_data=Path("/tmp/unused"),
        limits=Limits(done=2),
    )
    board = Board(
        active={
            1: done(1, "oldest", 9),
            2: done(2, "newest", 12),
            3: done(3, "middle", 10),
        }
    )

    _, _, dones = board_columns(config, board)

    assert dones == ["[2] newest", "[3] middle"]
