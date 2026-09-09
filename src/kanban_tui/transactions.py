"""Compatibility wrappers for the application transaction API.

New adapter code should construct ``BoardApplication`` once and inject it.
These config-based functions remain for third-party callers until version 1.0.0.
"""

from collections.abc import Callable

import click

from . import application as _application
from .application import BoardApplication, StoreError
from .deprecations import warn_legacy_api
from .models import Board
from .results import OperationResult
from .settings import AppConfig
from .storage import YamlBoardStore


def mutate_board(
    config: AppConfig,
    operation: Callable[[Board], OperationResult],
    *,
    expected_tasks: tuple[_application.TaskExpectation, ...] = (),
) -> tuple[Board, OperationResult]:
    warn_legacy_api(
        "kanban_tui.transactions.mutate_board()",
        "BoardApplication.mutate() with an injected BoardStore",
    )
    try:
        return BoardApplication(YamlBoardStore(config)).mutate(
            operation, expected_tasks=expected_tasks
        )
    except StoreError as exc:
        raise click.ClickException(str(exc)) from exc


def undo_board(config: AppConfig) -> Board:
    warn_legacy_api(
        "kanban_tui.transactions.undo_board()",
        "BoardApplication.undo() with an injected BoardStore",
    )
    try:
        return BoardApplication(YamlBoardStore(config)).undo()
    except StoreError as exc:
        raise click.ClickException(str(exc)) from exc


__all__ = [  # noqa: F822 - deprecated names are resolved by __getattr__
    "TaskConflict",
    "TaskExpectation",
    "mutate_board",
    "undo_board",
]


def __getattr__(name: str) -> object:
    compatibility_types: dict[str, tuple[object, str]] = {
        "TaskConflict": (
            _application.TaskConflict,
            "kanban_tui.application.TaskConflict",
        ),
        "TaskExpectation": (
            _application.TaskExpectation,
            "kanban_tui.application.TaskExpectation",
        ),
    }
    if name in compatibility_types:
        value, replacement = compatibility_types[name]
        warn_legacy_api(f"kanban_tui.transactions.{name}", replacement, stacklevel=2)
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
