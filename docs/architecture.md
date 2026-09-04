# Architecture

## Package layout

Production code lives under `src/kanban_tui/`.

- `__init__.py` — package version lookup.
- `cli.py` — Click command definitions, command-prefix handling, and user-facing wiring.
- `config.py` — config path resolution, YAML parsing, defaults, and validation.
- `models.py` — typed domain models: `TaskState`, `Task`, `Limits`, `AppConfig`, and `Board`.
- `services.py` — task creation, deletion, promotion/regression, and WIP/business rules.
- `storage.py` — datastore locking, YAML deserialization/serialization, and atomic writes.
- `rendering.py` — Rich table construction and terminal rendering.

Tests live under `tests/` and mirror these responsibilities where practical. Shared temporary-home/config fixtures live in `tests/conftest.py`.

## Runtime flow

1. A Click command in `cli.py` loads `AppConfig` through `config.py`.
2. The datastore lock is acquired in `storage.py`.
3. YAML is read and converted into a typed `Board`.
4. `services.py` mutates the board using domain objects and invariants.
5. The board is serialized back to the legacy-compatible YAML shape and atomically replaced on disk.
6. If `repaint` is enabled, the board is rendered through `rendering.py`.

## Task states

`TaskState` defines the only supported states:

- `todo`
- `inprogress`
- `done`
- `deleted`

Normal progression is `todo -> inprogress -> done`. Regression moves in the opposite direction. Deletion moves a task from the active collection to the deleted collection.

Every transition into `inprogress` enforces the configured WIP limit.

## Configuration

Configuration is read from `.clikan.yaml` under `CLIKAN_HOME`, falling back to the user's home directory.

Supported values:

- `clikan_data`: datastore path.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum done items displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: whether to display the board after mutations; default `false`.

`clikan configure` creates a minimal default configuration. An example lives at `examples/clikan.yaml`.

## Datastore format

The public on-disk format remains YAML-compatible with the original list representation so existing `.clikan.dat` files do not require migration.

Example:

```yaml
data:
  1:
    - todo
    - Example task
    - 2026-Sep-04 10:00:00
    - 2026-Sep-04 10:00:00
deleted: {}
```

The storage layer converts this representation into `Task` and `Board` objects immediately after reading. Business logic does not depend on positional list indexes.

## Persistence and locking

Each datastore uses a sibling `<datastore>.lock` directory as an inter-process lock. The owner PID is written inside the lock directory when possible.

Writes use a temporary file in the datastore directory, flush and `fsync` the contents, then replace the datastore with `os.replace()`. This keeps replacement atomic on the same filesystem and preserves the previous valid file if writing the temporary file fails.

## Versioning and packaging

Packaging is defined entirely in `pyproject.toml` with a `src/` layout. The installed console entry point is:

```text
clikan = kanban_tui.cli:clikan
```

The distribution version is sourced from the root `VERSION` file during builds. At runtime, installed package metadata is preferred; source checkouts fall back to the same `VERSION` file.
