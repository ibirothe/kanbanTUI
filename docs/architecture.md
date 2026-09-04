# Architecture

## Package layout

Production code lives under `src/kanban_tui/`.

- `__init__.py` — package version lookup.
- `cli.py` — Click command definitions, global board/config selection, metadata/transfer/undo commands, and user-facing wiring.
- `config.py` — config path resolution, named-board paths, YAML parsing/writing, defaults, validation, and supported config edits.
- `models.py` — typed domain models: `TaskState`, `TaskPriority`, `Task`, `Limits`, `AppConfig`, and `Board`.
- `services.py` — task creation, deletion, editing, metadata, state transitions, ordering, and board business rules.
- `storage.py` — datastore locking, YAML deserialization/serialization, atomic writes, and one-level undo snapshots.
- `transfer.py` — complete versioned JSON export/import validation and merge behavior.
- `rendering.py` — Rich, plain, JSON, metadata filtering, sorting, and history rendering.
- `tui.py` — Textual full-screen interface that reuses the same config, services, storage, and rendering helpers.

Tests live under `tests/` and mirror these responsibilities where practical. Shared temporary-home/config fixtures live in `tests/conftest.py`; explicit multi-board behavior is covered in `tests/test_multiboard.py` and `tests/test_board_config_cli.py`, metadata in `tests/test_metadata.py`, transfer behavior in `tests/test_transfer.py`, undo semantics in `tests/test_undo.py`, and Textual behavior is exercised headlessly in `tests/test_tui.py`.

## Runtime flow

For mutating commands and TUI actions:

1. The root command resolves the selected default, named, or explicit configuration path.
2. `config.py` loads and validates it into `AppConfig`.
3. An exclusive datastore writer lock is acquired in `storage.py`.
4. YAML is read and converted into a typed `Board`.
5. `services.py` applies the requested operation and returns a structured result containing messages plus success/failure counts.
6. Successful mutations serialize the board and atomically replace the datastore while retaining the immediately previous complete board under `_undo`.
7. The CLI prints service messages or the TUI refreshes the live board; failed requested operations remain non-zero in CLI mode.

`show`, `history`, export, and normal TUI reads are read-only and do not acquire the writer lock. Atomic datastore replacement means readers observe either the previous complete file or the new complete file. Showing a board whose datastore does not yet exist returns an empty board without creating a file; the first mutating command initializes persistence.

## Interactive TUI

`kanban-tui tui` runs a Textual application with TODO, IN PROGRESS, and DONE columns. Selection, search, editing, metadata, state movement, archiving, restoring, reprioritization, and undo are UI actions only; they do not duplicate business rules.

The TUI calls the same service and persistence functions used by Click commands, so capacity limits, validation, metadata normalization, timestamps, ordering, ID integrity, locking, undo behavior, and persistence semantics remain identical across interfaces. Dynamic `ListView` refreshes await Textual DOM updates before assigning selection/focus, which keeps keyboard operation deterministic and supports headless `App.run_test()` tests.

## Task states and limits

`TaskState` defines the only supported states:

- `todo`
- `inprogress`
- `done`
- `deleted`

Normal progression is `todo -> inprogress -> done`. Direct state commands can target TODO, IN PROGRESS, or DONE through shared transition logic. Deletion moves a task from the active collection to the deleted collection. `restore` moves a deleted task back to TODO while preserving its ID, creation timestamp, priority, and tags.

Capacity limits are invariants on entry into a constrained state: every transition into `inprogress` enforces `limits.wip`, and every transition into `todo` enforces `limits.todo` when configured.

Task IDs are unique across both active and deleted history. New IDs are allocated above the highest ID present in either collection, so deleted IDs are never reused.

## Manual ordering

TODO and IN PROGRESS tasks persist a numeric `position`. Legacy four-field task records remain valid; their task ID is used as the initial position when no explicit position is stored. New writes add the position as the fifth record field.

Within TODO and IN PROGRESS, rendering uses `(position, id)` ordering. Reordering compacts positions to deterministic consecutive values. New tasks and tasks entering a manually ordered state are placed at the bottom of that state. DONE remains ordered by `modified_at` descending, which represents completion/last-transition time.

Priority is intentionally independent from manual position; assigning `urgent` does not reorder a task automatically.

## Lightweight task metadata

`TaskPriority` supports four optional values: `low`, `normal`, `high`, and `urgent`. A task with no priority stores `None`.

Tags are optional normalized lowercase slugs. Valid tags are 1–32 characters, begin with a letter or number, and may otherwise contain lowercase letters, numbers, `-`, or `_`. Tags are deduplicated and stored deterministically.

Metadata mutations update `modified_at`, use the normal writer lock and undo mechanism, and apply only to active tasks. Archiving/restoring preserves metadata.

Rendering shows metadata inline (`!urgent`, `#backend`) and structured outputs expose `priority` and `tags` fields. `show --priority` and `show --tag` filter without mutating the board. General search also matches task text, tags, and priority values.

The TUI exposes priority cycling and complete tag-set editing through the same service functions used by the CLI.

## Configuration and board selection

The application has three configuration-selection modes:

1. `--config PATH` selects an explicit YAML file.
2. `--board NAME` selects `$KANBAN_TUI_HOME/boards/<name>.yaml`.
3. With neither option, `$KANBAN_TUI_HOME/.kanban-tui.yaml` is used when the environment variable is set; otherwise `~/.kanban-tui.yaml` is used.

`--config` and `--board` are mutually exclusive. The selected path applies to every command, including `configure`, `config`, `show`, mutations, `history`, transfer, `undo`, and `tui`.

Named board names are normalized to lowercase and restricted to a safe slug alphabet. `board create NAME` creates the board config and matching default `.dat` path; `board list` enumerates named boards and marks the currently selected path when it is part of the list.

The `config` command group exposes supported settings without requiring direct YAML editing:

- `config path` prints the selected YAML path.
- `config show` prints normalized values.
- `config set KEY VALUE` edits supported keys, validates the complete resulting document, and atomically replaces the config file.

Config edits preserve unrelated YAML fields. Optional TODO/WIP limits may be cleared with `unlimited`; other limits remain required non-negative integers.

Supported configuration values:

- `data_path`: datastore path.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum done items displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: whether to display the board after mutations; default `false`.

`data_path` path semantics are deterministic:

- absolute paths are used as supplied;
- `~` is expanded using the user's home directory;
- relative paths are resolved relative to the directory containing the selected configuration file, never relative to the shell's current working directory.

Config-file writes use a temporary sibling file, flush and `fsync`, and then `os.replace()` so config editing has the same atomic-replacement property as board persistence.

## Datastore format and timestamps

Task records are compact YAML lists for simple local persistence. A task with metadata may look like:

```yaml
data:
  1:
    - todo
    - Example task
    - '2026-09-04T10:00:00+02:00'
    - '2026-09-04T09:00:00+02:00'
    - 1
    - priority: urgent
      tags:
        - backend
        - bug
deleted: {}
```

The first five fields are state, text, modified timestamp, creation timestamp, and manual position. The optional sixth field is a metadata mapping containing `priority` and/or `tags`. Tasks without metadata remain five-field records. Older four-field records remain readable and acquire an explicit position on their next write.

New writes use timezone-aware ISO 8601 timestamps. The model boundary also accepts the earlier timestamp form such as `2026-Sep-04 10:00:00`. Naive timestamps are interpreted in the machine's local timezone for that date and normalized to timezone-aware `datetime` values inside the domain model.

`created_at` is the original task creation time. `modified_at` is the time of the most recent edit, metadata change, or state transition. DONE tasks are ordered by `modified_at` descending, so `limits.done` selects the most recently modified/completed DONE tasks.

## Undo snapshots

The datastore may contain an internal top-level `_undo` mapping in addition to `data` and `deleted`. `Board.from_mapping()` intentionally ignores this internal key, so normal reads operate only on the current board.

Before each successful mutation, the complete previously persisted board is captured under `_undo` and written together with the new board in one atomic datastore replacement. Failed and no-op mutations do not replace the snapshot.

`undo` validates `_undo`, atomically replaces the current board with that snapshot, and removes `_undo` in the resulting file. The design deliberately provides one undo level and no redo chain. Because board data and undo data share the same file replacement, there is no cross-file partial-update window.

## Complete transfer format

`transfer.py` defines a versioned JSON format separate from the view-oriented `show --format json` output.

The current envelope is identified by:

```json
{
  "format": "kanbanTUI-board",
  "version": 1
}
```

A complete export contains every active and archived task, including ID, state, text, creation/modification timestamps, manual position, priority, and tags. Priority/tags are optional on import, so earlier version-1 exports remain valid. DONE display limits, search filters, and temporary view sorting never affect exports.

Imports are fully parsed into a `Board` before persistence. `replace` substitutes the selected board; `merge` keeps the current board and adds imported tasks after rejecting all ID collisions. TODO/WIP capacity limits are validated on the complete candidate board before writing. Successful imports participate in the same undo mechanism as other mutations.

Export files are written through a temporary sibling file plus `fsync` and `os.replace()`. Existing files require explicit `--force` overwrite.

## Persistence and locking

Mutating commands use a sibling `<datastore>.lock` directory as an inter-process writer lock. The owner PID is written inside the lock directory when possible.

On POSIX systems, an existing lock whose recorded owner PID no longer exists is considered stale and recovered. When live-PID detection is unavailable or owner metadata is missing, a lock older than five minutes is treated as stale. A live writer lock still prevents another writer from entering the read-modify-write transaction.

Normal and exceptional command completion removes the writer lock. Read-only commands do not take this exclusive lock.

Writes use a temporary file in the datastore directory, flush and `fsync` the contents, then replace the datastore with `os.replace()`. This keeps replacement atomic on the same filesystem and preserves the previous valid file if writing the temporary file fails.

## Local installation

Project metadata and local installation configuration live in `pyproject.toml` with a `src/` layout. The installed console entry point is:

```text
kanban-tui = kanban_tui.cli:main
```

The project version is sourced from the root `VERSION` file. Runtime source checkouts use that same local version value.
