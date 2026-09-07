import click
import pytest

from kanban_tui.config import validate_board_name
from kanban_tui.models import Board
from kanban_tui.results import OperationCode
from kanban_tui.services import delete_tasks, restore_tasks


def test_non_positive_task_ids_are_invalid(write_config):
    config = write_config()

    delete_result = delete_tasks(Board(), ["0", "-1"])
    restore_result = restore_tasks(config.policy, Board(), ["0", "-1"])

    assert [item.code for item in delete_result.items] == [
        OperationCode.INVALID_TASK_ID,
        OperationCode.INVALID_TASK_ID,
    ]
    assert [item.raw_id for item in delete_result.items] == ["0", "-1"]
    assert [item.code for item in restore_result.items] == [
        OperationCode.INVALID_TASK_ID,
        OperationCode.INVALID_TASK_ID,
    ]


def test_default_board_name_is_reserved():
    with pytest.raises(click.ClickException, match="reserved"):
        validate_board_name("default")

    with pytest.raises(click.ClickException, match="reserved"):
        validate_board_name(" DEFAULT ")
