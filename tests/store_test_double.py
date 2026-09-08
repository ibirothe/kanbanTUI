from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy

from kanban_tui.application import BoardStore, BoardTransaction, StoreError
from kanban_tui.idempotency import MAX_IMPORT_RECEIPTS, ImportReceipt
from kanban_tui.models import Board


class MemoryBoardTransaction:
    def __init__(self, store: "MemoryBoardStore") -> None:
        self.store = store

    def load(self) -> Board:
        self.store.loads += 1
        return deepcopy(self.store.board)

    def commit(self, board: Board, *, previous: Board) -> None:
        self.store.commits += 1
        self.store.board = deepcopy(board)
        self.store.previous = deepcopy(previous)

    def undo(self) -> Board:
        self.store.undos += 1
        if self.store.previous is None:
            raise StoreError("Nothing to undo.")
        restored = deepcopy(self.store.previous)
        self.store.board = deepcopy(restored)
        self.store.previous = None
        return restored

    def find_import_receipt(self, key_digest: str) -> ImportReceipt | None:
        return next(
            (
                receipt
                for receipt in reversed(self.store.import_receipts)
                if receipt.key_digest == key_digest
            ),
            None,
        )

    def commit_import(
        self, board: Board, *, previous: Board, receipt: ImportReceipt
    ) -> None:
        self.store.commits += 1
        if receipt.changed:
            self.store.board = deepcopy(board)
            self.store.previous = deepcopy(previous)
        receipts = [
            existing
            for existing in self.store.import_receipts
            if existing.key_digest != receipt.key_digest
        ]
        self.store.import_receipts = [*receipts, receipt][-MAX_IMPORT_RECEIPTS:]


class MemoryBoardStore:
    def __init__(self, board: Board | None = None) -> None:
        self.board = deepcopy(board) if board is not None else Board()
        self.previous: Board | None = None
        self.reads = 0
        self.transactions = 0
        self.loads = 0
        self.commits = 0
        self.undos = 0
        self.locked = False
        self.import_receipts: list[ImportReceipt] = []

    def read(self) -> Board:
        self.reads += 1
        return deepcopy(self.board)

    @contextmanager
    def transaction(self) -> Iterator[BoardTransaction]:
        if self.locked:
            raise StoreError("Store is locked.")
        self.transactions += 1
        self.locked = True
        try:
            yield MemoryBoardTransaction(self)
        finally:
            self.locked = False


class RecordingTransaction:
    def __init__(self, store: "RecordingStore", inner: BoardTransaction) -> None:
        self.store = store
        self.inner = inner

    def load(self) -> Board:
        self.store.loads += 1
        return self.inner.load()

    def commit(self, board: Board, *, previous: Board) -> None:
        self.store.commits += 1
        self.inner.commit(board, previous=previous)

    def undo(self) -> Board:
        self.store.undos += 1
        return self.inner.undo()

    def find_import_receipt(self, key_digest: str) -> ImportReceipt | None:
        return self.inner.find_import_receipt(key_digest)

    def commit_import(
        self, board: Board, *, previous: Board, receipt: ImportReceipt
    ) -> None:
        self.store.commits += 1
        self.inner.commit_import(board, previous=previous, receipt=receipt)


class RecordingStore:
    def __init__(self, inner: BoardStore) -> None:
        self.inner = inner
        self.reads = 0
        self.transactions = 0
        self.loads = 0
        self.commits = 0
        self.undos = 0

    def read(self) -> Board:
        self.reads += 1
        return self.inner.read()

    @contextmanager
    def transaction(self) -> Iterator[BoardTransaction]:
        self.transactions += 1
        with self.inner.transaction() as transaction:
            yield RecordingTransaction(self, transaction)


class FailOnceTransaction:
    def __init__(self, store: "FailOnceCommitStore", inner: BoardTransaction) -> None:
        self.store = store
        self.inner = inner

    def load(self) -> Board:
        return self.inner.load()

    def commit(self, board: Board, *, previous: Board) -> None:
        self.store.attempts += 1
        if self.store.attempts == 1:
            raise StoreError("simulated write failure")
        self.inner.commit(board, previous=previous)

    def undo(self) -> Board:
        return self.inner.undo()

    def find_import_receipt(self, key_digest: str) -> ImportReceipt | None:
        return self.inner.find_import_receipt(key_digest)

    def commit_import(
        self, board: Board, *, previous: Board, receipt: ImportReceipt
    ) -> None:
        self.store.attempts += 1
        if self.store.attempts == 1:
            raise StoreError("simulated write failure")
        self.inner.commit_import(board, previous=previous, receipt=receipt)


class FailOnceCommitStore:
    def __init__(self, inner: BoardStore) -> None:
        self.inner = inner
        self.attempts = 0

    def read(self) -> Board:
        return self.inner.read()

    @contextmanager
    def transaction(self) -> Iterator[BoardTransaction]:
        with self.inner.transaction() as transaction:
            yield FailOnceTransaction(self, transaction)
