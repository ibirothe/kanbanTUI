# Architecture

## Package layout

Production code lives under `src/kanban_tui/`.

- `__init__.py` — application version lookup.
- `cli.py` — Click commands, command-prefix handling, config selection, and user-facing wiring.
- `config.py` — config path resolution, YAML parsing, defaults, and validation.
- `models.py` — typed domain models: `TaskState`, `Task`, `Limits`, `AppConfig`, and `Board`.
- `services.py` — task operations and board invariants.
- `storage.py` — datastore locking, YAML conversion, and atomic writes.
- `rendering.py` — Rich table, plain text, JSON, and history rendering.

Tests live under `tests/` and mirror these responsibilities. Shared temporary-home/config fixtures live in `tests/conftest.py`, and multi-board behavior is covered in `tests/test_multiboard.py`.

## Runtime flow

For mutating commands:

1. The root command selects a configuration path.
2. `config.py` loads and validates it into `AppConfig`.
3. `storage.py` acquires an exclusive writer lock.
4. YAML is loaded into a typed `Board`.
5. `services.py` applies the operation and returns an `OperationResult`.
6. The board is serialized and atomically replaced on disk.
7. The CLI prints messages, optionally repaints, and returns non-zero if any requested operation failed.

`show` and `history` are read-only and do not acquire the writer lock. Atomic datastore replacement means readers observe complete files. A missing datastore is displayed as an empty board and is created on the first mutating command.

## Task states and limits

Supported states:

- `todo`
- `inprogress`
- `done`
- `deleted`

Normal progression is `todo -> inprogress -> done`. Regression moves in the opposite direction. Deletion moves a task to the deleted collection. `restore` returns a deleted task to TODO while preserving its ID and creation time.

Capacity limits are invariants on entry into constrained states: `limits.wip` applies whenever a task enters `inprogress`, and `limits.todo` applies whenever a task enters `todo`.

Task IDs are unique across active and deleted tasks. New IDs are allocated above the highest ID in either collection.

## Configuration and board selection

Configuration precedence:

1. explicit root option `--config PATH`;
2. `$KANBAN_TUI_HOME/.kanban-tui.yaml` when `KANBAN_TUI_HOME` is set;
3. `~/.kanban-tui.yaml`.

The root option applies to every subcommand:

```text
kanban-tui --config ~/boards/work.yaml show
kanban-tui --config ~/boards/personal.yaml add Buy groceries
```

`kanban-tui --config PATH configure` creates the selected configuration path and uses the same basename with `.dat` as the default datastore.

Supported configuration values:

- `data_path`: datastore path.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum completed tasks displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: whether to display the board after successful mutations; default `false`.

Path semantics:

- absolute paths are used as supplied;
- `~` expands to the user's home directory;
- relative `data_path` values resolve against the selected configuration file directory.

The example configuration is `examples/kanban-tui.yaml`.

## Datastore and timestamps

The datastore is YAML with `data` and `deleted` mappings. Each task record stores state, text, modification time, and creation time.

New writes use timezone-aware ISO 8601 timestamps:

```yaml
data:
  1:
    - todo
    - Example task
    - '2026-09-04T10:00:00+02:00'
    - '2026-09-04T09:00:00+02:00'
deleted: {}
```

Older timestamp strings are parsed at the model boundary and normalized to timezone-aware `datetime` values. New writes always serialize ISO 8601 timestamps.

`created_at` is the original creation time. `modified_at` is the time of the most recent edit or state transition. Completed tasks are ordered by `modified_at` descending.

## Persistence and locking

Mutating commands use a sibling `<datastore>.lock` directory as an inter-process writer lock. The owner PID is stored when possible.

On POSIX systems, a lock whose recorded PID is no longer running is recovered. When PID detection is unavailable or owner metadata is missing, locks older than five minutes are treated as stale. Live writers block other writers.

Writes use a temporary file in the datastore directory, flush and `fsync` it, then replace the datastore with `os.replace()`. This keeps replacement atomic on the same filesystem.

## Local project configuration

`pyproject.toml` defines local installation metadata, runtime dependencies, the `kanban-tui` console entry point, and development tooling. The application version is sourced from `VERSION`.
