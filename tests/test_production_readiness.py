import click
import pytest

from kanban_tui.config import validate_board_name
from kanban_tui.models import Board
from kanban_tui.services import delete_tasks, restore_tasks


def test_non_positive_task_ids_are_invalid(write_config):
    config = write_config()

    delete_result = delete_tasks(Board(), ["0", "-1"])
    restore_result = restore_tasks(config, Board(), ["0", "-1"])

    assert delete_result.messages == [
        "Error: invalid task ID '0'.",
        "Error: invalid task ID '-1'.",
    ]
    assert restore_result.messages == [
        "Error: invalid task ID '0'.",
        "Error: invalid task ID '-1'.",
    ]


def test_default_board_name_is_reserved():
    with pytest.raises(click.ClickException, match="reserved"):
        validate_board_name("default")

    with pytest.raises(click.ClickException, match="reserved"):
        validate_board_name(" DEFAULT ")
