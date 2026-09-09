from datetime import datetime, timezone

import pytest

from kanban_tui.application import TaskConflict, TaskExpectation
from kanban_tui.results import OperationCode, OperationResult
from kanban_tui.services import add_tasks, edit_task
from kanban_tui.storage import read_data
from tests.application_test_support import yaml_application


def test_conflict_prevents_operation_and_preserves_snapshot(write_config):
    config = write_config()
    board, _ = yaml_application(config).mutate(
        lambda b: add_tasks(config.policy, b, ["one"])
    )
    expected = TaskExpectation.capture(board.active[1])
    yaml_application(config).mutate(
        lambda b: edit_task(config.policy, b, "1", "external")
    )
    original = config.data_path.read_bytes()

    def must_not_run(board):
        pytest.fail("Conflicting operation ran")

    with pytest.raises(TaskConflict) as caught:
        yaml_application(config).mutate(must_not_run, expected_tasks=(expected,))
    assert caught.value.code is OperationCode.TASK_CONFLICT
    assert caught.value.board.active[1].text == "external"
    assert config.data_path.read_bytes() == original
    assert yaml_application(config).undo().active[1].text == "one"


def test_expectation_is_detached_and_accepts_persistence_roundtrip(write_config):
    config = write_config()
    board, _ = yaml_application(config).mutate(
        lambda b: add_tasks(config.policy, b, ["one"])
    )
    expected = TaskExpectation.capture(board.active[1])
    board.active[1].text = "unpersisted local edit"
    current, result = yaml_application(config).mutate(
        lambda b: edit_task(config.policy, b, "1", "two"),
        expected_tasks=(expected,),
    )
    assert result.succeeded == 1
    assert current.active[1].text == "two"


def test_failed_and_noop_transactions_preserve_snapshot(write_config):
    config = write_config()
    yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["one"])
    )
    original = config.data_path.read_bytes()
    yaml_application(config).mutate(lambda board: add_tasks(config.policy, board, [""]))
    yaml_application(config).mutate(lambda board: OperationResult())
    assert config.data_path.read_bytes() == original
    assert not yaml_application(config).undo().active


@pytest.mark.parametrize(
    "edit_time",
    [
        datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 6, 12, 0, 2, tzinfo=timezone.utc),
    ],
)
def test_identical_edit_preserves_datastore_and_previous_undo(
    write_config, monkeypatch, edit_time
):
    config = write_config()
    initial_time = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("kanban_tui.services.timestamp", lambda: initial_time)
    yaml_application(config).mutate(lambda b: add_tasks(config.policy, b, ["same"]))
    original_modified_at = read_data(config).active[1].modified_at
    original_bytes = config.data_path.read_bytes()
    monkeypatch.setattr("kanban_tui.services.timestamp", lambda: edit_time)

    current, result = yaml_application(config).mutate(
        lambda b: edit_task(config.policy, b, "1", "  same  ")
    )

    assert [item.code for item in result.items] == [OperationCode.TASK_UNCHANGED]
    assert current.active[1].modified_at == original_modified_at
    assert config.data_path.read_bytes() == original_bytes
    assert not yaml_application(config).undo().active


def test_partial_batch_is_one_undo_and_exception_releases_lock(write_config):
    config = write_config()

    def fail(board):
        add_tasks(config.policy, board, ["never persisted"])
        raise ValueError("operation failed")

    with pytest.raises(ValueError, match="operation failed"):
        yaml_application(config).mutate(fail)
    assert not config.data_path.exists()
    board, result = yaml_application(config).mutate(
        lambda board: add_tasks(config.policy, board, ["one", "", "two"])
    )
    assert (result.succeeded, result.failed) == (2, 1)
    assert len(board.active) == 2
    assert not yaml_application(config).undo().active
