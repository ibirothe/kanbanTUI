import pytest

from kanban_tui.services import OperationResult, add_tasks
from kanban_tui.storage import read_data
from kanban_tui.transactions import mutate_board, undo_board


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


def test_failed_and_noop_transactions_preserve_snapshot(write_config):
    config = write_config()
    mutate_board(config, lambda board: add_tasks(config, board, ["one"]))
    original = config.data_path.read_bytes()
    mutate_board(config, lambda board: add_tasks(config, board, [""]))
    mutate_board(config, lambda board: OperationResult(succeeded=1))
    assert config.data_path.read_bytes() == original
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
