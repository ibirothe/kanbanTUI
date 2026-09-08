import pytest

from kanban_tui.application import (
    BoardApplication,
    StoreError,
    TaskConflict,
    TaskExpectation,
)
from kanban_tui.idempotency import digest_idempotency_key, digest_import_request
from kanban_tui.imports import ImportMode
from kanban_tui.policy import BoardPolicy
from kanban_tui.results import OperationCode
from kanban_tui.services import add_tasks, edit_task
from kanban_tui.storage import YamlBoardStore
from tests.store_test_double import MemoryBoardStore, RecordingStore


@pytest.fixture(params=["yaml", "memory"])
def application_store(request, write_config):
    if request.param == "yaml":
        inner = YamlBoardStore(write_config())
    else:
        inner = MemoryBoardStore()
    store = RecordingStore(inner)
    return BoardApplication(store), store


def test_store_contract_partial_batch_single_commit_and_detached_undo(
    application_store,
):
    application, store = application_store

    board, result = application.mutate(
        lambda current: add_tasks(
            policy=_policy(), board=current, tasks=["one", "", "two"]
        )
    )

    assert (result.changed, result.rejected) == (2, 1)
    assert store.loads == 1
    assert store.commits == 1
    board.active[1].text = "detached caller mutation"
    assert application.read().active[1].text == "one"
    assert not application.undo().active
    assert store.undos == 1


def test_store_contract_noop_and_exception_roll_back_and_release_writer(
    application_store,
):
    application, store = application_store
    application.mutate(lambda board: add_tasks(_policy(), board, ["one"]))
    commits = store.commits

    _, unchanged = application.mutate(
        lambda board: edit_task(_policy(), board, "1", " one ")
    )
    assert unchanged.unchanged == 1
    assert store.commits == commits

    def fail(board):
        board.active[1].text = "must roll back"
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        application.mutate(fail)
    assert application.read().active[1].text == "one"

    application.mutate(lambda board: edit_task(_policy(), board, "1", "after"))
    assert application.read().active[1].text == "after"


def test_store_contract_read_is_not_a_writer_transaction(application_store):
    application, store = application_store

    assert not application.read().active
    assert store.reads == 1
    assert store.transactions == 0


def test_store_contract_conflict_is_typed_and_releases_writer(application_store):
    application, store = application_store
    board, _ = application.mutate(
        lambda current: add_tasks(_policy(), current, ["one"])
    )
    expected = TaskExpectation.capture(board.active[1])
    application.mutate(lambda current: edit_task(_policy(), current, "1", "external"))
    commits = store.commits

    with pytest.raises(TaskConflict) as caught:
        application.mutate(
            lambda current: edit_task(_policy(), current, "1", "stale"),
            expected_tasks=(expected,),
        )
    assert caught.value.code is OperationCode.TASK_CONFLICT
    assert caught.value.task_id == 1
    assert store.commits == commits

    application.mutate(lambda current: edit_task(_policy(), current, "1", "after"))
    assert application.read().active[1].text == "after"


def test_store_contract_undo_without_snapshot_is_port_error(application_store):
    application, _ = application_store

    with pytest.raises(StoreError, match="Nothing to undo"):
        application.undo()
    application.mutate(lambda board: add_tasks(_policy(), board, ["after error"]))
    assert application.read().active[1].text == "after error"


def test_import_use_case_runs_with_memory_store_without_file_adapter():
    application = BoardApplication(MemoryBoardStore())
    application.mutate(lambda board: add_tasks(_policy(), board, ["current"]))
    imported = MemoryBoardStore().read()
    add_tasks(_policy(), imported, ["imported"])

    merged, result = application.import_board(
        _policy(), imported, ImportMode.MERGE, source="memory"
    )

    assert [item.code for item in result.items] == [
        OperationCode.IMPORT_COMPLETED,
        OperationCode.IDS_REMAPPED,
    ]
    assert result.items[1].id_mapping == ((1, 2),)
    assert [task.text for task in merged.active.values()] == ["current", "imported"]
    assert [task.text for task in application.undo().active.values()] == ["current"]

    replaced, result = application.import_board(
        _policy(), imported, ImportMode.REPLACE, source="memory"
    )
    assert [item.code for item in result.items] == [OperationCode.IMPORT_COMPLETED]
    assert [task.text for task in replaced.active.values()] == ["imported"]


def test_keyed_noop_preserves_undo_and_receipt_across_store_contract(
    application_store,
):
    application, store = application_store
    board, _ = application.mutate(
        lambda current: add_tasks(_policy(), current, ["one"])
    )

    _, first = application.import_board_once(
        _policy(),
        board,
        ImportMode.REPLACE,
        key_digest=digest_idempotency_key("request-1"),
        request_digest=digest_import_request("replace", b"payload"),
    )
    _, replay = application.import_board_once(
        _policy(),
        board,
        ImportMode.REPLACE,
        key_digest=digest_idempotency_key("request-1"),
        request_digest=digest_import_request("replace", b"payload"),
    )

    assert first.unchanged == 1
    assert replay.unchanged == 1
    assert store.commits == 2
    assert not application.undo().active

    board_after_undo, after_undo_replay = application.import_board_once(
        _policy(),
        board,
        ImportMode.REPLACE,
        key_digest=digest_idempotency_key("request-1"),
        request_digest=digest_import_request("replace", b"payload"),
    )
    assert after_undo_replay.unchanged == 1
    assert not board_after_undo.active
    assert store.commits == 2


def _policy():
    return BoardPolicy()
