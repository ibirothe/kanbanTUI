"""Application transaction boundaries shared by terminal adapters."""

from collections.abc import Callable
from copy import deepcopy

from .models import AppConfig, Board
from .services import OperationResult
from .storage import datastore_lock, read_data, undo_last_change, write_data


def mutate_board(
    config: AppConfig, operation: Callable[[Board], OperationResult]
) -> tuple[Board, OperationResult]:
    with datastore_lock(config):
        board = read_data(config)
        previous = deepcopy(board)
        result = operation(board)
        if result.succeeded and board.to_mapping() != previous.to_mapping():
            write_data(config, board, previous=previous)
        else:
            board = previous
    return board, result


def undo_board(config: AppConfig) -> Board:
    with datastore_lock(config):
        return undo_last_change(config)
