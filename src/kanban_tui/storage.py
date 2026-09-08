import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

import click
import yaml

from .application import BoardTransaction, StoreError
from .atomic import atomic_text_writer
from .codec import DatastoreDocument, dump_datastore, load_datastore
from .idempotency import MAX_IMPORT_RECEIPTS, ImportReceipt
from .models import Board
from .resources import resolve_board_paths
from .settings import AppConfig


class _LockUnavailable(Exception):
    """Raised when another process currently owns the datastore lock."""


def _ensure_lock_byte(lock_file: BinaryIO) -> None:
    lock_file.seek(0, os.SEEK_END)
    if lock_file.tell() == 0:
        lock_file.write(b"\0")
        lock_file.flush()
    lock_file.seek(0)


def _acquire_file_lock(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise _LockUnavailable from exc
        return

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        raise _LockUnavailable from exc


def _release_file_lock(lock_file: BinaryIO) -> None:
    lock_file.seek(0)
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def datastore_lock(config: AppConfig):
    """Hold one OS-backed exclusive writer lock for a datastore transaction."""
    try:
        paths = resolve_board_paths(config.data_path)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    data_path, lock_path = paths.data, paths.lock
    lock_file: BinaryIO | None = None

    try:
        data_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a+b")
        _ensure_lock_byte(lock_file)
        _acquire_file_lock(lock_file)
    except _LockUnavailable as exc:
        if lock_file is not None:
            lock_file.close()
        raise click.ClickException(
            f"Datastore {data_path} is locked by another kanban-tui process."
        ) from exc
    except OSError as exc:
        if lock_file is not None:
            lock_file.close()
        raise click.ClickException(
            f"Could not lock datastore {data_path}: {exc}"
        ) from exc

    try:
        yield
    finally:
        assert lock_file is not None
        _release_file_lock(lock_file)
        lock_file.close()


def _read_document(data_path: Path) -> DatastoreDocument:
    try:
        with data_path.open("r", encoding="utf-8") as stream:
            try:
                return load_datastore(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Datastore {data_path} contains invalid YAML: {exc}"
                ) from exc
            except UnicodeError:
                raise
            except ValueError as exc:
                raise click.ClickException(f"Datastore {data_path}: {exc}") from exc
    except UnicodeError as exc:
        raise click.ClickException(
            f"Datastore {data_path} must use valid UTF-8 encoding."
        ) from exc
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise click.ClickException(
            f"Could not read datastore {data_path}: {exc}"
        ) from exc


def _atomic_write_document(
    data_path: Path,
    board: Board,
    previous: Board | None = None,
    import_receipts: tuple[ImportReceipt, ...] = (),
) -> None:
    try:
        with atomic_text_writer(data_path) as outfile:
            dump_datastore(outfile, board, previous, import_receipts)
    except (OSError, yaml.YAMLError) as exc:
        raise click.ClickException(
            f"Could not write datastore {data_path}: {exc}"
        ) from exc


def read_data(config: AppConfig, *, initialize_missing: bool = False) -> Board:
    """Read the datastore without creating files or emitting user-facing output."""
    data_path = config.data_path
    try:
        document = _read_document(data_path)
    except FileNotFoundError:
        return Board()
    return document.board


def write_data(
    config: AppConfig,
    board: Board,
    *,
    snapshot_previous: bool = False,
    previous: Board | None = None,
) -> None:
    try:
        document = _read_document(config.data_path)
    except FileNotFoundError:
        document = DatastoreDocument(Board())
    if previous is None and snapshot_previous:
        previous = document.board
    _atomic_write_document(
        config.data_path,
        board,
        previous,
        document.import_receipts,
    )


def undo_last_change(config: AppConfig) -> Board:
    data_path = config.data_path
    try:
        document = _read_document(data_path)
    except FileNotFoundError as exc:
        raise click.ClickException("Nothing to undo.") from exc

    if document.previous is None:
        raise click.ClickException("Nothing to undo.")

    previous = document.previous
    _atomic_write_document(
        data_path,
        previous,
        import_receipts=document.import_receipts,
    )
    return previous


class YamlBoardTransaction:
    """Writer-side implementation of the application transaction port."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._document: DatastoreDocument | None = None

    def _load_document(self) -> DatastoreDocument:
        if self._document is None:
            try:
                self._document = _read_document(self.config.data_path)
            except FileNotFoundError:
                self._document = DatastoreDocument(Board())
        return self._document

    def load(self) -> Board:
        return self._load_document().board

    def commit(self, board: Board, *, previous: Board) -> None:
        document = self._load_document()
        _atomic_write_document(
            self.config.data_path,
            board,
            previous,
            document.import_receipts,
        )

    def undo(self) -> Board:
        document = self._load_document()
        if document.previous is None:
            raise click.ClickException("Nothing to undo.")
        previous = document.previous
        _atomic_write_document(
            self.config.data_path,
            previous,
            import_receipts=document.import_receipts,
        )
        return previous

    def find_import_receipt(self, key_digest: str) -> ImportReceipt | None:
        return next(
            (
                receipt
                for receipt in reversed(self._load_document().import_receipts)
                if receipt.key_digest == key_digest
            ),
            None,
        )

    def commit_import(
        self, board: Board, *, previous: Board, receipt: ImportReceipt
    ) -> None:
        document = self._load_document()
        retained = tuple(
            existing
            for existing in document.import_receipts
            if existing.key_digest != receipt.key_digest
        )
        receipts = (*retained, receipt)[-MAX_IMPORT_RECEIPTS:]
        undo = previous if receipt.changed else document.previous
        _atomic_write_document(self.config.data_path, board, undo, receipts)


class YamlBoardStore:
    """YAML-backed adapter for the application-owned board store port."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def read(self) -> Board:
        try:
            return read_data(self.config, initialize_missing=False)
        except click.ClickException as exc:
            raise StoreError(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[BoardTransaction]:
        try:
            with datastore_lock(self.config):
                transaction: BoardTransaction = YamlBoardTransaction(self.config)
                yield transaction
        except click.ClickException as exc:
            raise StoreError(str(exc)) from exc
