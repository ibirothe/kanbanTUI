import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kanban_tui.cli import main
from kanban_tui.models import (
    AppConfig,
    Board,
    Limits,
    Task,
    TaskPriority,
    TaskState,
)
from kanban_tui.rendering import format_json, format_plain, task_display_text, visible_tasks
from kanban_tui.services import add_tasks, set_task_priority, set_task_tags, update_task_tag
from kanban_tui.storage import datastore_lock, read_data, write_data
from kanban_tui.transfer import board_from_export, export_payload
from kanban_tui.tui import KanbanApp


STAMP = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)
EARLIER = datetime(2026, 9, 4, 9, 0, tzinfo=timezone.utc)


def config() -> AppConfig:
    return AppConfig(Path("/tmp/unused"), limits=Limits())


def task(task_id: int = 1) -> Task:
    return Task(task_id, TaskState.TODO, "metadata task", STAMP, EARLIER)


def test_legacy_five_field_record_remains_metadata_free():
    raw = {
        "data": {
            1: [
                "todo",
                "legacy",
                "2026-09-04T10:00:00+00:00",
                "2026-09-04T09:00:00+00:00",
                1,
            ]
        },
        "deleted": {},
    }

    board = Board.from_mapping(raw)

    assert board.active[1].priority is None
    assert board.active[1].tags == ()
    assert board.to_mapping() == raw


def test_metadata_round_trip_uses_optional_sixth_record_field():
    original = Task(
        1,
        TaskState.TODO,
        "task",
        STAMP,
        EARLIER,
        priority=TaskPriority.HIGH,
        tags=("Backend", "bug"),
    )
    board = Board(active={1: original})

    raw = board.to_mapping()
    restored = Board.from_mapping(raw)

    assert raw["data"][1][5] == {"priority": "high", "tags": ["backend", "bug"]}
    assert restored.active[1].priority is TaskPriority.HIGH
    assert restored.active[1].tags == ("backend", "bug")


def test_invalid_tags_are_rejected():
    with pytest.raises(ValueError, match="tags must be"):
        Task(
            1,
            TaskState.TODO,
            "task",
            STAMP,
            EARLIER,
            tags=("not a tag",),
        )


def test_metadata_services_update_without_changing_manual_order():
    board = Board(active={1: task(1), 2: task(2)})
    board.active[1].position = 1
    board.active[2].position = 2

    priority_result = set_task_priority(board, "1", TaskPriority.URGENT)
    tags_result = set_task_tags(board, "1", ["Backend", "bug", "backend"])
    remove_result = update_task_tag(board, "1", "remove", "bug")

    assert priority_result.ok
    assert tags_result.ok
    assert remove_result.ok
    assert board.active[1].priority is TaskPriority.URGENT
    assert board.active[1].tags == ("backend",)
    assert [item.id for item in board.ordered_tasks(TaskState.TODO)] == [1, 2]


def test_rendering_and_filters_include_metadata():
    first = task(1)
    first.priority = TaskPriority.HIGH
    first.tags = ("backend", "bug")
    second = task(2)
    board = Board(active={1: first, 2: second})

    by_priority = visible_tasks(config(), board, priority_filter=TaskPriority.HIGH)
    by_tag = visible_tasks(config(), board, tag_filter="backend")
    by_search = visible_tasks(config(), board, search="HIGH")
    payload = json.loads(format_json(config(), board))
    plain = format_plain(config(), board)

    assert [item.id for item in by_priority] == [1]
    assert [item.id for item in by_tag] == [1]
    assert [item.id for item in by_search] == [1]
    assert payload["tasks"][0]["priority"] == "high"
    assert payload["tasks"][0]["tags"] == ["backend", "bug"]
    assert "priority\ttags" in plain.splitlines()[0]
    assert "!high" in task_display_text(first)
    assert "#backend" in task_display_text(first)


def test_transfer_preserves_optional_metadata():
    item = task(1)
    item.priority = TaskPriority.URGENT
    item.tags = ("ops",)

    restored = board_from_export(export_payload(Board(active={1: item})))

    assert restored.active[1].priority is TaskPriority.URGENT
    assert restored.active[1].tags == ("ops",)


def test_cli_priority_tags_filters_and_undo(runner, write_config):
    config_value = write_config()
    runner.invoke(main, ["add", "first"])
    runner.invoke(main, ["add", "second"])

    priority_result = runner.invoke(main, ["priority", "1", "urgent"])
    tag_result = runner.invoke(main, ["tag", "add", "1", "Backend"])
    filtered = runner.invoke(main, ["show", "--tag", "backend", "--format", "json"])

    assert priority_result.exit_code == 0
    assert "priority to urgent" in priority_result.output
    assert tag_result.exit_code == 0
    assert "#backend" in tag_result.output
    assert [item["id"] for item in json.loads(filtered.output)["tasks"]] == [1]

    persisted = read_data(config_value, initialize_missing=False)
    assert persisted.active[1].priority is TaskPriority.URGENT
    assert persisted.active[1].tags == ("backend",)

    undo = runner.invoke(main, ["undo"])
    assert undo.exit_code == 0
    restored = read_data(config_value, initialize_missing=False)
    assert restored.active[1].priority is TaskPriority.URGENT
    assert restored.active[1].tags == ()


def seed_board(config_value: AppConfig) -> None:
    board = Board()
    add_tasks(config_value, board, ["interactive"])
    with datastore_lock(config_value):
        write_data(config_value, board)


async def test_tui_cycles_priority_and_sets_tags(write_config):
    config_value = write_config()
    seed_board(config_value)
    app = KanbanApp(config_value)

    async with app.run_test() as pilot:
        await pilot.pause()
        await app.action_cycle_priority()
        await app._tags_prompt_result(1, "Backend, ui")

        assert app.board.active[1].priority is TaskPriority.LOW
        assert app.board.active[1].tags == ("backend", "ui")
        await app._search_prompt_result("backend")
        assert app._selected_task().id == 1

    persisted = read_data(config_value, initialize_missing=False)
    assert persisted.active[1].priority is TaskPriority.LOW
    assert persisted.active[1].tags == ("backend", "ui")
