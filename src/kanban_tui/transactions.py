"""Compatibility wrappers for the application transaction API.

New adapter code should construct ``BoardApplication`` once and inject it.
These config-based functions remain temporarily for third-party callers.
"""

from collections.abc import Callable

import click

from .application import BoardApplication, StoreError, TaskConflict, TaskExpectation
from .models import Board
from .results import OperationResult
from .settings import AppConfig
from .storage import YamlBoardStore


def mutate_board(
    config: AppConfig,
    operation: Callable[[Board], OperationResult],
    *,
    expected_tasks: tuple[TaskExpectation, ...] = (),
) -> tuple[Board, OperationResult]:
    try:
        return BoardApplication(YamlBoardStore(config)).mutate(
            operation, expected_tasks=expected_tasks
        )
    except StoreError as exc:
        raise click.ClickException(str(exc)) from exc


def undo_board(config: AppConfig) -> Board:
    try:
        return BoardApplication(YamlBoardStore(config)).undo()
    except StoreError as exc:
        raise click.ClickException(str(exc)) from exc


__all__ = ["TaskConflict", "TaskExpectation", "mutate_board", "undo_board"]
