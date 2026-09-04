# Architecture

## Package layout

Production code lives under `src/kanban_tui/`.

- `__init__.py` — package version lookup.
- `cli.py` — Click command definitions, command-prefix handling, global config selection, and user-facing wiring.
- `config.py` — config path resolution, YAML parsing, defaults, and validation.
- `models.py` — typed domain models: `TaskState`, `Task`, `Limits`, `AppConfig`, and `Board`.
- `services.py` — task creation, deletion, promotion/regression, and board business rules.
- `storage.py` — datastore locking, YAML deserialization/serialization, and atomic writes.
- `rendering.py` — Rich, plain, JSON, and history rendering.

Tests live under `tests/` and mirror these responsibilities where practical. Shared temporary-home/config fixtures live in `tests/conftest.py`; explicit multi-board behavior is covered separately in `tests/test_multiboard.py`.

## Runtime flow

For mutating commands:

1. The root Click command selects a configuration path.
2. `config.py` loads and validates that configuration into `AppConfig`.
3. An exclusive datastore writer lock is acquired in `storage.py`.
4. YAML is read and converted into a typed `Board`.
5. `services.py` applies the requested operation and returns a structured result containing messages plus success/failure counts.
6. The board is serialized back to the YAML persistence shape and atomically replaced on disk.
7. The CLI prints service messages, repaints after successful changes when configured, and returns non-zero if any requested operation failed.

`show` and `history` are read-only and do not acquire the writer lock. Atomic datastore replacement means readers observe either the previous complete file or the new complete file. Showing a board whose datastore does not yet exist returns an empty board without creating a file; the first mutating command initializes persistence.

## Task states and limits

`TaskState` defines the only supported states:

- `todo`
- `inprogress`
- `done`
- `deleted`

Normal progression is `todo -> inprogress -> done`. Regression moves in the opposite direction. Deletion moves a task from the active collection to the deleted collection. `restore` moves a deleted task back to TODO while preserving its ID and creation timestamp.

Capacity limits are invariants on entry into a constrained state: every transition into `inprogress` enforces `limits.wip`, and every transition into `todo` enforces `limits.todo` when configured.

Task IDs are unique across both active and deleted history. New IDs are allocated above the highest ID present in either collection, so deleted IDs are never reused.

## Configuration and board selection

Configuration selection is deterministic and has one precedence order:

1. explicit root option `--config PATH`;
2. `$CLIKAN_HOME/.clikan.yaml` when `CLIKAN_HOME` is set;
3. `~/.clikan.yaml`.

The root option applies to every subcommand, including `configure`, `show`, mutations, and `history`. This allows multiple independent boards without mutating environment variables:

```text
clikan --config ~/boards/work.yaml show
clikan --config ~/boards/personal.yaml add Buy groceries
```

`clikan --config PATH configure` creates the selected configuration path and uses the same basename with `.dat` as its default datastore. For example, `/home/user/boards/work.yaml` defaults to `/home/user/boards/work.dat`.

Supported configuration values:

- `clikan_data`: datastore path.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum done items displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: whether to display the board after mutations; default `false`.

`clikan_data` path semantics are deterministic:

- absolute paths are used as supplied;
- `~` is expanded using the user's home directory;
- relative paths are resolved relative to the directory containing the selected configuration file, never relative to the shell's current working directory.

Default `clikan configure` creates a missing `CLIKAN_HOME` directory when necessary and writes a minimal configuration. An example lives at `examples/clikan.yaml`. Missing datastore parent directories are created when a writer first initializes the board.

## Datastore format and timestamps

The public on-disk structure remains YAML-compatible with the original list representation so existing `.clikan.dat` files do not require a manual migration.

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

The model boundary also accepts the legacy timestamp form such as `2026-Sep-04 10:00:00`. Legacy naive timestamps are interpreted in the machine's local timezone for that date and normalized to timezone-aware `datetime` values inside the domain model. The next write serializes them as ISO 8601.

`created_at` is the original task creation time. `modified_at` is the time of the most recent edit or state transition. DONE tasks are ordered by `modified_at` descending, so `limits.done` selects the most recently completed tasks rather than relying on task-ID or dictionary order.

The storage layer converts the YAML representation into `Task` and `Board` objects immediately after reading. Business logic does not depend on positional list indexes or opaque timestamp strings.

## Persistence and locking

Mutating commands use a sibling `<datastore>.lock` directory as an inter-process writer lock. The owner PID is written inside the lock directory when possible.

On POSIX systems, an existing lock whose recorded owner PID no longer exists is considered stale and recovered. When live-PID detection is unavailable or owner metadata is missing, a lock older than five minutes is treated as stale. A live writer lock still prevents another writer from entering the read-modify-write transaction.

Normal and exceptional command completion removes the writer lock. Read-only commands do not take this exclusive lock.

Writes use a temporary file in the datastore directory, flush and `fsync` the contents, then replace the datastore with `os.replace()`. This keeps replacement atomic on the same filesystem and preserves the previous valid file if writing the temporary file fails.

## Versioning and packaging

Packaging is defined entirely in `pyproject.toml` with a `src/` layout. The installed console entry point is:

```text
clikan = kanban_tui.cli:clikan
```

The distribution version is sourced from the root `VERSION` file during builds. At runtime, installed package metadata is preferred; source checkouts fall back to the same `VERSION` file.
