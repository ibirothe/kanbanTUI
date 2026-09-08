import pytest

from kanban_tui import transactions, transfer
from kanban_tui.application import TaskExpectation
from kanban_tui.config import get_app_home
from kanban_tui.services import add_tasks
from kanban_tui.transfer_format import export_payload


def test_transaction_wrappers_warn_and_remain_functional(write_config):
    config = write_config()

    with pytest.warns(DeprecationWarning, match="removed in kanbanTUI 1.0.0"):
        board, _ = transactions.mutate_board(
            config, lambda current: add_tasks(config.policy, current, ["one"])
        )
    with pytest.warns(DeprecationWarning, match="removed in kanbanTUI 1.0.0"):
        restored = transactions.undo_board(config)

    assert board.active[1].text == "one"
    assert not restored.active


def test_legacy_type_and_transfer_exports_warn_with_canonical_replacements():
    with pytest.warns(DeprecationWarning, match="application.TaskExpectation"):
        legacy_expectation = transactions.TaskExpectation
    with pytest.warns(DeprecationWarning, match="transfer_format.export_payload"):
        legacy_export_payload = transfer.export_payload

    assert legacy_expectation is TaskExpectation
    assert legacy_export_payload is export_payload


def test_legacy_combined_home_warns(monkeypatch, tmp_path):
    monkeypatch.setenv("KANBAN_TUI_HOME", str(tmp_path))

    with pytest.warns(DeprecationWarning, match="removed in kanbanTUI 1.0.0"):
        app_home = get_app_home()

    assert app_home == tmp_path
