# Architecture

## Target environment

kanbanTUI is a terminal-first Python application with Arch Linux as the primary developer desktop target. End-user installation is designed around the Arch `python-pipx` package and a Git source install, keeping application dependencies isolated from Arch's externally managed system Python.

The runtime dependency set is deliberately small: Click, PyYAML, Rich, and Textual. The root CLI is implemented directly with `click.Group`; no default-group extension is required.

## Package layout

Production code lives under `src/kanban_tui/`:

- `cli.py` — Click command surface, native prefix/board completion, board/config selection, transfer and undo wiring.
- `config.py` — XDG/portable/legacy path resolution, named boards, YAML validation and atomic config writes.
- `models.py` — typed domain model and persistence-schema invariants.
- `services.py` — task mutations and workflow/capacity business rules.
- `storage.py` — side-effect-free reads, cross-process writer locking, atomic YAML writes and undo.
- `transfer.py` — complete JSON export/import, validation and merge ID remapping.
- `rendering.py` — table, plain and JSON views, filters and sorting.
- `tui.py` — Textual full-screen UI using the same services and persistence layer as the CLI.

Tests live under `tests/`. Focused suites cover models, services, storage, transfer, CLI, configuration, multi-board behavior, metadata, undo, TUI behavior, Arch/XDG integration and production-readiness invariants.

## CLI behavior

The root command is a normal `click.Group` with `invoke_without_command=True`. Running `kanban-tui` without a subcommand calls the normal board display path, while explicit commands use the same group and unique-prefix resolution.

Click's built-in shell completion protocol is used for Bash, Zsh and Fish. Choice/path parameters inherit Click completion, and `--board` adds dynamic completion from existing named board configs. Completion scripts are generated from the installed `kanban-tui` entry point and require no additional runtime package.

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

A `Task` has a positive integer ID, a supported state, non-empty text, timezone-aware creation/modification timestamps, a positive manual position, optional priority/tags, and an optional completion timestamp.

`completed_at` is valid for DONE tasks and may be retained in archived history. TODO and IN PROGRESS tasks cannot carry a completion timestamp.

`Board` requires positive integer mapping keys, matching `Task.id` values, valid active/deleted bucket states, and no ID overlap between active and archived collections. New task IDs are allocated above complete active and archived history and are never reused.

## Ordering and completion time

TODO and IN PROGRESS use persistent numeric `position` ordering. Reordering normalizes positions to consecutive values. Already-satisfied reorder requests are semantic no-ops and therefore do not alter timestamps, persistence or undo history.

DONE is ordered by `completed_at` descending. Entering DONE sets the timestamp; leaving DONE clears it; re-entering DONE creates a new completion time. Later text, priority or tag edits update `modified_at` without changing completion order.

Legacy DONE records without `completed_at` use their existing `modified_at` as the migration fallback and persist an explicit completion timestamp on their next write.

## XDG configuration and board selection

Fresh Linux installs use:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/config.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/board.dat
```

Fresh named boards use:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/boards/<name>.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/boards/<name>.dat
```

Selection semantics are:

1. `--config PATH` selects an explicit file.
2. `--board NAME` selects a named-board config.
3. `KANBAN_TUI_HOME`, when set, switches to a portable single-root layout.
4. Otherwise the XDG config path is used.
5. If no XDG config exists, an existing legacy `~/.kanban-tui.yaml` is discovered. Legacy named boards below `~/boards/` remain discoverable as well.

This fallback is read-path compatibility rather than the layout for new installs: fresh `configure` and `board create` operations use XDG paths unless `KANBAN_TUI_HOME` or an explicit config path is selected.

`--config` and `--board` are mutually exclusive. Named boards are lowercase slugs; `default` is reserved for the implicit default board.

`data_path` is expanded and resolved deterministically. Relative paths are relative to the configuration file, never to the current shell directory. A config is rejected if its resolved `data_path` points back to the config file itself.

Limits are strict non-negative integers (digit strings remain accepted for existing configs). Fractional numeric values are rejected rather than truncated. TODO/WIP may be configured as unlimited through the config command layer.

Config writes use a sibling temporary file, flush, `fsync` and `os.replace()`.

## Persistence and locking

Datastore reads are side-effect free. A missing datastore returns `Board()` and remains absent until a mutation succeeds.

Writers coordinate through a sibling `<datastore>.lock` file using OS-managed advisory locks:

- POSIX: `fcntl.flock(..., LOCK_EX | LOCK_NB)`;
- Windows: `msvcrt.locking(..., LK_NBLCK, 1)`.

The lock file may remain on disk as a harmless coordination file; ownership is held by the operating-system lock associated with the open file descriptor. Closing the descriptor or process termination releases the lock.

Datastore writes use a temporary file in the datastore directory, flush and `fsync`, then `os.replace()` the destination. Readers therefore observe a complete old or complete new file, not a partially written board.

## Datastore schema

The current YAML task record is a compact list. The first five fields are state, text, modified time, creation time and manual position. An optional sixth mapping carries priority, tags and/or completion time.

Valid legacy four-field records remain readable. Legacy timestamps are accepted and normalized to timezone-aware `datetime` values. Numeric positions and IDs are validated strictly; fractional values are not coerced.

## Undo

The datastore may contain a top-level `_undo` mapping. `Board.from_mapping()` ignores that internal key during normal reads.

Each successful semantic mutation writes the new board and immediately previous board snapshot together in one atomic replacement. Failed operations, already-satisfied reorders and imports that result in no effective board change do not replace the undo snapshot.

`undo` restores `_undo` and removes the snapshot, intentionally providing one undo level and no redo chain.

## Transfer format

Complete transfer uses the versioned `kanbanTUI-board` JSON envelope, version 1. Exports include all active and archived tasks independent of view filters or DONE display limits.

Imports are parsed into the validated domain model before persistence. Imported tasks must satisfy the selected board's `limits.taskname`, and the final candidate board must satisfy TODO/WIP capacities.

`replace` preserves imported IDs. `merge` preserves non-conflicting IDs and deterministically remaps collisions against active or archived history. Export refuses destinations that resolve to the selected board's config file, datastore or datastore lock file.

## TUI safety

The Textual TUI calls the same services and storage functions as the CLI. Validation, capacity rules, locking, undo, metadata normalization and ordering therefore have one implementation.

Prompt input is routed through shared service validation, including restore IDs.

## Arch installation model

Arch owns the system Python and `pipx` executable:

```text
pacman -> python-pipx + git
```

pipx owns the isolated kanbanTUI virtual environment and user-facing `kanban-tui` executable:

```text
pipx install git+https://github.com/ibirothe/kanbanTUI.git
```

No system-site `pip install` is part of the end-user flow. Local development uses a project `.venv` and editable install.

## Local quality checks

```text
pytest
pytest --cov=kanban_tui --cov-report=term-missing
ruff check .
ruff format --check .
mypy src/kanban_tui
```

No remote workflow is required by the project model.
