from datetime import datetime, timezone

import pytest

from kanban_tui.services import OperationResult, add_tasks, edit_task
from kanban_tui.storage import read_data
from kanban_tui.transactions import (
    TaskConflict,
    TaskExpectation,
    mutate_board,
    undo_board,
)


def test_transaction_reads_once_and_snapshots_detached_state(write_config, monkeypatch):
    config = write_config()
    reads = []

    def counted_read(config):
        reads.append(config)
        return read_data(config)

    monkeypatch.setattr("kanban_tui.transactions.read_data", counted_read)
    board, result = mutate_board(
        config, lambda board: add_tasks(config, board, ["one"])
    )
    assert result.succeeded == 1
    assert len(reads) == 1
    board.active[1].text = "changed in memory"
    assert not undo_board(config).active


def test_conflict_prevents_operation_and_preserves_snapshot(write_config):
    config = write_config()
    board, _ = mutate_board(config, lambda b: add_tasks(config, b, ["one"]))
    expected = TaskExpectation.capture(board.active[1])
    mutate_board(config, lambda b: edit_task(config, b, "1", "external"))
    original = config.data_path.read_bytes()

    def must_not_run(board):
        pytest.fail("Conflicting operation ran")

    with pytest.raises(TaskConflict) as caught:
        mutate_board(config, must_not_run, expected_tasks=(expected,))
    assert caught.value.board.active[1].text == "external"
    assert config.data_path.read_bytes() == original
    assert undo_board(config).active[1].text == "one"


def test_expectation_is_detached_and_accepts_persistence_roundtrip(write_config):
    config = write_config()
    board, _ = mutate_board(config, lambda b: add_tasks(config, b, ["one"]))
    expected = TaskExpectation.capture(board.active[1])
    board.active[1].text = "unpersisted local edit"
    current, result = mutate_board(
        config,
        lambda b: edit_task(config, b, "1", "two"),
        expected_tasks=(expected,),
    )
    assert result.succeeded == 1
    assert current.active[1].text == "two"


def test_failed_and_noop_transactions_preserve_snapshot(write_config):
    config = write_config()
    mutate_board(config, lambda board: add_tasks(config, board, ["one"]))
    original = config.data_path.read_bytes()
    mutate_board(config, lambda board: add_tasks(config, board, [""]))
    mutate_board(config, lambda board: OperationResult(succeeded=1))
    assert config.data_path.read_bytes() == original
    assert not undo_board(config).active


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
    mutate_board(config, lambda b: add_tasks(config, b, ["same"]))
    original_modified_at = read_data(config).active[1].modified_at
    original_bytes = config.data_path.read_bytes()
    monkeypatch.setattr("kanban_tui.services.timestamp", lambda: edit_time)

    current, result = mutate_board(
        config, lambda b: edit_task(config, b, "1", "  same  ")
    )

    assert result.messages == ["Task #1 is unchanged."]
    assert current.active[1].modified_at == original_modified_at
    assert config.data_path.read_bytes() == original_bytes
    assert not undo_board(config).active


def test_partial_batch_is_one_undo_and_exception_releases_lock(write_config):
    config = write_config()

    def fail(board):
        add_tasks(config, board, ["never persisted"])
        raise ValueError("operation failed")

    with pytest.raises(ValueError, match="operation failed"):
        mutate_board(config, fail)
    assert not config.data_path.exists()
    board, result = mutate_board(
        config, lambda board: add_tasks(config, board, ["one", "", "two"])
    )
    assert (result.succeeded, result.failed) == (2, 1)
    assert len(board.active) == 2
    assert not undo_board(config).active
