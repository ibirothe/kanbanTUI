import os
import subprocess
import sys
from pathlib import Path


def test_domain_and_services_import_without_adapter_dependencies():
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import builtins
import sys

blocked = {"click", "pathlib", "rich", "textual", "yaml"}
real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.partition(".")[0] in blocked:
        raise AssertionError(f"adapter dependency imported: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import

from kanban_tui.application import BoardApplication, BoardStore, BoardTransaction
from kanban_tui.models import Board, Task, TaskState
from kanban_tui.policy import BoardPolicy
from kanban_tui.results import OperationCode, OperationStatus
from kanban_tui.services import add_tasks

board = Board()
result = add_tasks(BoardPolicy(task_text_limit=4), board, ["core"])
assert result.succeeded == 1
assert result.items[0].code is OperationCode.TASK_ADDED
assert result.items[0].status is OperationStatus.CHANGED
assert not hasattr(result, "messages")
assert "kanban_tui.operation_messages" not in sys.modules
assert BoardApplication is not None
assert BoardStore is not None
assert BoardTransaction is not None
assert isinstance(board.active[1], Task)
assert board.active[1].state is TaskState.TODO
"""
    env = dict(os.environ, PYTHONPATH=str(source_root))

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_transfer_format_imports_without_adapter_dependencies():
    source_root = Path(__file__).resolve().parents[1] / "src"
    script = """
import builtins
import sys

blocked = {"click", "http", "pathlib", "socketserver", "textual", "yaml"}
real_import = builtins.__import__

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.partition(".")[0] in blocked:
        raise AssertionError(f"adapter dependency imported: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import

from kanban_tui.models import Board
from kanban_tui.transfer_format import (
    TransferFormatError,
    board_from_export,
    export_payload,
)

payload = export_payload(Board())
assert board_from_export(payload) == Board()
try:
    board_from_export({"format": "other", "version": 1, "active": [], "archived": []})
except TransferFormatError:
    pass
else:
    raise AssertionError("invalid transfer payload was accepted")
assert "click" not in sys.modules
assert "pathlib" not in sys.modules
"""
    env = dict(os.environ, PYTHONPATH=str(source_root))

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
