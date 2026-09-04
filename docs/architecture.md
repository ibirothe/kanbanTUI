# Architecture

## Package layout

Production code lives under `src/kanban_tui/`:

- `cli.py` — Click command surface, board/config selection, transfer and undo wiring.
- `config.py` — configuration paths, named boards, YAML validation and atomic config writes.
- `models.py` — typed domain model and persistence-schema invariants.
- `services.py` — task mutations and workflow/capacity business rules.
- `storage.py` — side-effect-free reads, cross-process writer locking, atomic YAML writes and undo.
- `transfer.py` — complete JSON export/import, validation and merge ID remapping.
- `rendering.py` — table, plain and JSON views, filters and sorting.
- `tui.py` — Textual full-screen UI using the same services and persistence layer as the CLI.

Tests live under `tests/`. Shared isolated-home fixtures are in `tests/conftest.py`; focused suites cover models, services, storage, transfer, CLI, configuration, multi-board behavior, metadata, undo, TUI behavior and production-readiness invariants.

## Runtime flow

For a mutation:

1. The CLI or TUI resolves the selected configuration.
2. `config.py` validates it into `AppConfig`.
3. `storage.py` acquires an exclusive OS-backed datastore writer lock.
4. The YAML datastore is read into a validated `Board`. A missing datastore is represented as an empty board without creating files or printing output.
5. `services.py` applies the operation and returns `OperationResult`.
6. Only a successful semantic mutation writes the datastore.
7. The previous complete board is stored as the single `_undo` snapshot in the same atomic replacement.

Read-only operations (`show`, `history`, export and normal TUI reads) do not acquire the exclusive writer lock.

## Domain invariants

A `Task` has:

- positive integer `id`;
- state `todo`, `inprogress`, `done` or `deleted`;
- non-empty text;
- timezone-aware `created_at` and `modified_at`;
- positive integer manual `position`;
- optional priority and normalized tags;
- optional `completed_at`.

`completed_at` is valid for DONE tasks and may be retained in archived history. TODO and IN PROGRESS tasks cannot carry a completion timestamp.

`Board` enforces that:

- mapping keys are positive integer task IDs;
- each mapping key equals the contained `Task.id`;
- active tasks are not in `deleted` state;
- deleted-history entries are in `deleted` state;
- an ID cannot exist in both active and deleted collections.

New task IDs are always allocated above all active and archived history, so IDs are never reused.

## Ordering and completion time

TODO and IN PROGRESS use persistent numeric `position` ordering. Reordering normalizes positions to consecutive values. Already-satisfied reorder requests are semantic no-ops and therefore do not alter timestamps, persistence or undo history.

DONE is ordered by `completed_at` descending. Entering DONE sets the timestamp; leaving DONE clears it; re-entering DONE creates a new completion time. Later text, priority or tag edits update `modified_at` without changing completion order.

Legacy DONE records without `completed_at` use their existing `modified_at` as the migration fallback and persist an explicit completion timestamp on their next write.

## Configuration and board selection

Selection precedence is:

1. `--config PATH`;
2. `--board NAME` using `$KANBAN_TUI_HOME/boards/<name>.yaml`;
3. `$KANBAN_TUI_HOME/.kanban-tui.yaml`, or `~/.kanban-tui.yaml` when the environment variable is unset.

`--config` and `--board` are mutually exclusive. Named boards are lowercase slugs; `default` is reserved for the implicit default board and cannot be used as a named-board slug.

`data_path` is expanded and resolved deterministically. Relative paths are relative to the configuration file, never to the current shell directory. A config is rejected if its resolved `data_path` points back to the config file itself.

Limits are strict non-negative integers (digit strings remain accepted for existing configs). Fractional numeric values are rejected rather than truncated. TODO/WIP may be configured as unlimited through the config command layer.

Config writes use a sibling temporary file, flush, `fsync` and `os.replace()`.

## Persistence and locking

Datastore reads are side-effect free. A missing datastore returns `Board()` and remains absent until a mutation succeeds.

Writers coordinate through a sibling `<datastore>.lock` file using OS-managed advisory byte-range/file locks:

- POSIX: `fcntl.flock(..., LOCK_EX | LOCK_NB)`;
- Windows: `msvcrt.locking(..., LK_NBLCK, 1)`.

The lock file may remain on disk as a harmless coordination file; ownership is held by the operating-system lock associated with the open file descriptor. Closing the descriptor or process termination releases the lock, so there is no PID file or age-based stale-lock heuristic that could evict a live writer.

Datastore writes use a temporary file in the datastore directory, flush and `fsync`, then `os.replace()` the destination. Readers therefore observe a complete old or complete new file, not a partially written board.

## Datastore schema

The current YAML task record is a compact list:

```yaml
data:
  1:
    - done
    - Example task
    - '2026-09-04T10:30:00+02:00'
    - '2026-09-04T09:00:00+02:00'
    - 1
    - priority: urgent
      tags:
        - backend
      completed_at: '2026-09-04T10:00:00+02:00'
deleted: {}
```

The first five fields are state, text, modified time, creation time and manual position. The optional sixth mapping carries priority, tags and/or completion time.

Valid legacy four-field records remain readable. Legacy timestamps are accepted and normalized to timezone-aware `datetime` values. Numeric positions and IDs are validated strictly; fractional values are not coerced.

## Undo

The datastore may contain a top-level `_undo` mapping. `Board.from_mapping()` ignores that internal key during normal reads.

Each successful semantic mutation writes the new board and immediately previous board snapshot together in one atomic replacement. Failed operations, already-satisfied reorders and imports that result in no effective board change do not replace the undo snapshot.

`undo` restores `_undo` and removes the snapshot, intentionally providing one undo level and no redo chain.

## Transfer format

Complete transfer uses the versioned JSON envelope:

```json
{
  "format": "kanbanTUI-board",
  "version": 1
}
```

Exports include all active and archived tasks, independent of view filters or DONE display limits. They include IDs, state, text, timestamps, position, priority and tags.

Imports are parsed into the validated domain model before persistence. In addition to schema validation, imported tasks must satisfy the selected board's `limits.taskname`, and the final candidate board must satisfy TODO/WIP capacities.

`replace` preserves imported IDs. `merge` preserves non-conflicting IDs and deterministically remaps collisions against active or archived history. The CLI reports remapped IDs.

Export refuses destinations that resolve to the selected board's config file, datastore or datastore lock file, preventing `--force` from overwriting internal board state.

## TUI safety

The Textual TUI calls the same services and storage functions as the CLI. Validation, capacity rules, locking, undo, metadata normalization and ordering therefore have one implementation.

Prompt input is routed through shared service validation. In particular, invalid restore IDs are reported through the normal operation-result path rather than being converted with an unsafe callback-level `int()` call.

## Local quality checks

The repository defines local development checks in `pyproject.toml`:

```text
pytest
pytest --cov=kanban_tui --cov-report=term-missing
ruff check .
ruff format --check .
mypy src/kanban_tui
```

No remote workflow is required by the project model.
