"""Application use cases and persistence ports independent of terminal adapters."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import ContextManager, Protocol, runtime_checkable

from .idempotency import ImportReceipt
from .imports import ImportMode, merge_boards
from .models import Board, Task, TaskPriority, TaskState
from .policy import BoardPolicy, validate_imported_board
from .results import OperationCode, OperationResult


class BoardTransaction(Protocol):
    """Writer transaction with one detached working board and atomic commit."""

    def load(self) -> Board: ...

    def commit(self, board: Board, *, previous: Board) -> None: ...

    def undo(self) -> Board: ...


@runtime_checkable
class IdempotentBoardTransaction(BoardTransaction, Protocol):
    """Optional transaction capability for atomic board/import receipts."""

    def find_import_receipt(self, key_digest: str) -> ImportReceipt | None: ...

    def commit_import(
        self, board: Board, *, previous: Board, receipt: ImportReceipt
    ) -> None: ...


class BoardStore(Protocol):
    """Application-owned persistence port."""

    def read(self) -> Board: ...

    def transaction(self) -> ContextManager[BoardTransaction]: ...


class StoreError(Exception):
    """Infrastructure failure translated at the application port boundary."""


class IdempotencyConflict(Exception):
    """One idempotency key was reused for a different import request."""


@dataclass(frozen=True)
class TaskExpectation:
    """Detached comparison of the complete task state represented in a store."""

    task_id: int
    archived: bool
    state: TaskState
    text: str
    modified_at: datetime
    created_at: datetime
    position: int
    priority: TaskPriority | None
    tags: tuple[str, ...]
    completed_at: datetime | None

    @classmethod
    def capture(cls, task: Task) -> "TaskExpectation":
        return cls(
            task.id,
            task.state is TaskState.DELETED,
            task.state,
            task.text,
            task.modified_at,
            task.created_at,
            task.position,
            task.priority,
            task.tags,
            task.completed_at,
        )

    def matches(self, board: Board) -> bool:
        tasks = board.deleted if self.archived else board.active
        task = tasks.get(self.task_id)
        return task is not None and self == self.capture(task)


class TaskConflict(Exception):
    """A snapshot-dependent command no longer matches the current task."""

    def __init__(self, board: Board, task_id: int) -> None:
        self.board = board
        self.task_id = task_id
        self.code = OperationCode.TASK_CONFLICT
        super().__init__(task_id)


class BoardApplication:
    """Shared read, mutation, import and undo use cases."""

    def __init__(self, store: BoardStore) -> None:
        self.store = store

    def read(self) -> Board:
        return self.store.read()

    def mutate(
        self,
        operation: Callable[[Board], OperationResult],
        *,
        expected_tasks: tuple[TaskExpectation, ...] = (),
    ) -> tuple[Board, OperationResult]:
        with self.store.transaction() as transaction:
            board = transaction.load()
            for expected in expected_tasks:
                if not expected.matches(board):
                    raise TaskConflict(board, expected.task_id)
            previous = deepcopy(board)
            result = operation(board)
            if result.changed and board != previous:
                transaction.commit(board, previous=previous)
            else:
                board = previous
        return board, result

    def import_board(
        self,
        policy: BoardPolicy,
        imported: Board,
        mode: ImportMode | str,
        *,
        source: str | None = None,
    ) -> tuple[Board, OperationResult]:
        selected_mode = ImportMode(mode)
        validate_imported_board(policy, imported)

        def apply_import(current: Board) -> OperationResult:
            return self._apply_import(
                policy, current, imported, selected_mode, source=source
            )

        return self.mutate(apply_import)

    def import_board_once(
        self,
        policy: BoardPolicy,
        imported: Board,
        mode: ImportMode | str,
        *,
        key_digest: str,
        request_digest: str,
    ) -> tuple[Board, OperationResult]:
        """Apply or replay one import atomically with its durable receipt."""
        selected_mode = ImportMode(mode)
        with self.store.transaction() as base_transaction:
            if not isinstance(base_transaction, IdempotentBoardTransaction):
                raise StoreError("Store does not support idempotent imports.")
            transaction = base_transaction
            board = transaction.load()
            existing = transaction.find_import_receipt(key_digest)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise IdempotencyConflict
                return board, self._result_from_receipt(existing)

            validate_imported_board(policy, imported)
            previous = deepcopy(board)
            result = self._apply_import(policy, board, imported, selected_mode)
            changed = bool(result.changed and board != previous)
            if not changed:
                board = previous
            receipt = ImportReceipt(
                key_digest=key_digest,
                request_digest=request_digest,
                mode=selected_mode.value,
                changed=changed,
                id_mapping=tuple(
                    sorted(
                        (source_id, destination_id)
                        for item in result.items
                        for source_id, destination_id in item.id_mapping
                    )
                ),
            )
            transaction.commit_import(board, previous=previous, receipt=receipt)
        return board, result

    @staticmethod
    def _apply_import(
        policy: BoardPolicy,
        current: Board,
        imported: Board,
        selected_mode: ImportMode,
        *,
        source: str | None = None,
    ) -> OperationResult:
        if selected_mode is ImportMode.REPLACE:
            target = deepcopy(imported)
            remapped: dict[int, int] = {}
        else:
            target, remapped = merge_boards(current, imported)

        result = OperationResult()
        if target == current:
            result.no_change(OperationCode.IMPORT_UNCHANGED)
            return result

        validate_imported_board(policy, target)
        current.active, current.deleted = target.active, target.deleted
        result.change(
            OperationCode.IMPORT_COMPLETED,
            text=source,
            action=selected_mode.value,
        )
        if remapped:
            result.no_change(
                OperationCode.IDS_REMAPPED,
                id_mapping=tuple(sorted(remapped.items())),
            )
        return result

    @staticmethod
    def _result_from_receipt(receipt: ImportReceipt) -> OperationResult:
        result = OperationResult()
        if receipt.changed:
            result.change(OperationCode.IMPORT_COMPLETED, action=receipt.mode)
        else:
            result.no_change(OperationCode.IMPORT_UNCHANGED)
        if receipt.id_mapping:
            result.no_change(
                OperationCode.IDS_REMAPPED,
                id_mapping=receipt.id_mapping,
            )
        return result

    def undo(self) -> Board:
        with self.store.transaction() as transaction:
            return transaction.undo()
