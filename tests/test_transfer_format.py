from datetime import datetime, timezone

import pytest

from kanban_tui.models import Board, Task, TaskState
from kanban_tui.transfer_format import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    TransferFormatError,
    board_from_export,
    export_payload,
)


def test_transport_neutral_codec_round_trips_complete_board():
    stamp = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    board = Board(
        active={1: Task(1, TaskState.TODO, "one", stamp, stamp, position=1)},
        deleted={2: Task(2, TaskState.DELETED, "old", stamp, stamp, position=2)},
    )

    payload = export_payload(board)
    restored = board_from_export(payload)

    assert payload["format"] == EXPORT_FORMAT
    assert payload["version"] == EXPORT_VERSION
    assert restored == board


def test_transport_neutral_codec_exposes_specific_format_error():
    with pytest.raises(TransferFormatError, match="unsupported export format"):
        board_from_export(
            {"format": "other", "version": 1, "active": [], "archived": []}
        )

    assert issubclass(TransferFormatError, ValueError)
