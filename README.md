# kanbanTUI

A terminal-based personal Kanban board for managing TODO, in-progress, completed, and archived tasks.

## Requirements

Python 3.11 or newer.

## Installation

Install from a checkout:

```bash
python -m pip install .
```

For local development:

```bash
python -m pip install -e ".[dev]"
```

## Configuration

Create the default configuration:

```bash
kanban-tui configure
```

The default configuration is `~/.kanban-tui.yaml`. An example is available at [`examples/kanban-tui.yaml`](examples/kanban-tui.yaml).

Supported settings:

- `data_path`: datastore path. Relative paths are resolved relative to the configuration file directory.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum completed tasks displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: display the board after successful mutations; default `false`.

Select a configuration in one of three ways:

1. `--config PATH` for an explicit YAML file;
2. `--board NAME` for a named board in `$KANBAN_TUI_HOME/boards/`;
3. otherwise `$KANBAN_TUI_HOME/.kanban-tui.yaml` or `~/.kanban-tui.yaml` is used.

`--config` and `--board` are mutually exclusive.

## Named boards

Create and list named boards:

```bash
kanban-tui board create work
kanban-tui board create personal
kanban-tui board list
```

Use a named board with any command, including the TUI:

```bash
kanban-tui --board work add Fix production bug
kanban-tui --board personal add Buy groceries
kanban-tui --board work show
kanban-tui --board work tui
```

Named board configurations live at `$KANBAN_TUI_HOME/boards/<name>.yaml`, with a matching `.dat` datastore by default. Board names are normalized lowercase slugs containing letters, numbers, `-`, or `_`.

The lower-level explicit config mechanism remains available:

```bash
kanban-tui --config ~/boards/custom.yaml configure
kanban-tui --config ~/boards/custom.yaml show
```

## Configuration commands

Inspect and edit the selected configuration without opening YAML manually:

```bash
kanban-tui config path
kanban-tui config show
kanban-tui config set limits.wip 3
kanban-tui config set limits.todo unlimited
kanban-tui config set repaint true
```

The same commands work with `--board` or `--config`:

```bash
kanban-tui --board work config set limits.wip 2
kanban-tui --config ~/boards/custom.yaml config show
```

Supported `config set` keys are `data_path`, `repaint`, `limits.todo`, `limits.wip`, `limits.done`, and `limits.taskname`. Optional TODO/WIP limits accept `unlimited`. Updates are validated before an atomic config-file replacement and preserve unrelated YAML fields.

## Interactive TUI

Launch the full-screen board with:

```bash
kanban-tui tui
```

The TUI uses the same configuration, datastore, validation, capacity limits, ordering rules, metadata, undo, and mutation services as the CLI.

Keyboard controls:

- `↑` / `↓` or `j` / `k`: select a task.
- `←` / `→` or `h` / `l`: move the selected task between TODO, IN PROGRESS, and DONE.
- `Shift+↑` / `Shift+↓`: reprioritize within TODO or IN PROGRESS.
- `a`: add a task.
- `e`: edit the selected task.
- `p`: cycle priority through none, low, normal, high, and urgent.
- `t`: replace the selected task's comma-separated tag set.
- `d`: archive the selected task.
- `r`: restore an archived task by ID.
- `u`: undo the last successful board mutation.
- `/`: search task text, tags, and priority.
- `c`: clear the current search filter.
- `?`: show keyboard help.
- `q`: quit.

The CLI remains available for scripting and one-shot operations.

## Usage

```bash
kanban-tui show
kanban-tui add Fix login bug
kanban-tui edit 1 Fix login timeout handling
kanban-tui priority 1 urgent
kanban-tui tag add 1 backend
kanban-tui tag remove 1 backend
kanban-tui tag clear 1
kanban-tui start 1
kanban-tui done 1
kanban-tui todo 1
kanban-tui move 1 top
kanban-tui move 3 before 1
kanban-tui delete 1
kanban-tui history
kanban-tui restore 1
kanban-tui undo
```

`start`, `done`, and `todo` move tasks directly to the requested state. The older `promote` and `regress` commands remain available as one-step transition shortcuts.

TODO and IN PROGRESS tasks have persistent manual ordering. Use `move <id> top`, `move <id> bottom`, `move <id> before <other-id>`, or `move <id> after <other-id>` to reprioritize a task within its current column. Completed tasks are ordered by the time they most recently entered DONE. Editing text, priority, or tags on a completed task does not make it appear newly completed.

`add` treats all words after the command as one task description. `edit` preserves task ID, state, creation time, manual position, priority, tags, and completion time. `history` lists archived tasks, and `restore` returns archived tasks to TODO while respecting configured capacity limits.

Successful mutations use short task-centric messages such as `Added #12`, `Started #12`, and `Completed #12`. Rejected operations begin with `Error:` and return a non-zero exit status. For multi-ID commands, the command returns non-zero if any requested operation fails.

Unique command prefixes are accepted only when unambiguous.

## Priority and tags

Metadata is intentionally lightweight and optional. A task may have one priority and zero or more tags.

Priority values are `low`, `normal`, `high`, and `urgent`; clear a priority with:

```bash
kanban-tui priority 12 clear
```

Tags are normalized to lowercase and must be 1–32 characters containing letters, numbers, `-`, or `_`. Priority and tags do not automatically change manual task order.

Table/TUI views render metadata inline, for example:

```text
[12] !urgent Fix production login #backend #bug
```

Filter metadata without mutating the board:

```bash
kanban-tui show --priority urgent
kanban-tui show --priority none
kanban-tui show --tag backend
kanban-tui show --state todo --tag bug --priority high
```

`--search` also searches tag names and priority values in addition to task text.

## Undo

kanbanTUI keeps one atomic undo snapshot per board. Every successful mutation records the complete board state that existed immediately before that mutation; failed or semantic no-op commands do not replace the snapshot.

```bash
kanban-tui add Temporary task
kanban-tui undo
```

Undo covers task creation, edits, metadata changes, state changes, ordering, archive/restore operations, mixed successful batches, and imports. Reorder requests that already describe the current order and imports that produce no board changes leave the previous undo snapshot intact. There is intentionally one undo level: after `undo`, there is no redo snapshot.

The interactive TUI exposes the same operation with `u`.

## Board export and import

`show --format json` is a filtered view and is not a backup format. Use the dedicated transfer commands for complete board portability:

```bash
kanban-tui export board.json
kanban-tui export board.json --force
kanban-tui import board.json --mode merge
kanban-tui import board.json --mode replace
```

The versioned `kanbanTUI-board` JSON format contains every active and archived task, including IDs, states, creation/modification/completion timestamps, manual positions, priority, and tags. It is independent of the DONE display limit and `show` filters.

`merge` preserves the current board and appends imported tasks. If an imported ID already exists in active or archived history, that imported task is deterministically assigned a fresh ID and the CLI reports the mapping, for example `#1->#8`. Non-conflicting imported IDs remain unchanged. `replace` replaces the selected board and preserves the imported IDs exactly.

Both modes validate the complete import and configured TODO/WIP capacities before writing. Imports that produce no effective board changes do not write the datastore or replace the current undo snapshot. A successful mutating import can be reverted with `undo`.

## Board view and filters

The table view renders one task per row, wraps long descriptions, shows TODO/WIP capacity, marks full columns, displays metadata, and provides actionable empty states.

`show` supports state, text, priority, and tag filtering without changing the board:

```bash
kanban-tui show --state todo
kanban-tui show --search login
kanban-tui show --priority urgent
kanban-tui show --tag backend
```

Search is case-insensitive. Manual task order is the default, but temporary sort views are available:

```bash
kanban-tui show --sort id
kanban-tui show --sort created
kanban-tui show --sort modified
```

Sorting changes only the current view; it does not rewrite persisted manual ordering.

## Output formats

```bash
kanban-tui show --format table
kanban-tui show --format plain
kanban-tui show --format json
```

- `table` is the default Rich terminal view.
- `plain` emits deterministic tab-separated text, including timestamps, priority, and tags, without color codes.
- `json` emits structured task data with timezone-aware ISO 8601 `created_at`, `modified_at`, and `completed_at` values plus priority and tags.

Filters and sorting apply consistently to all three formats. All formats use the configured completed-task display limit. Rich output honors `NO_COLOR`.

## Persistence behavior

Reading a board is side-effect free. If the selected datastore does not exist yet, read-only commands and TUI startup see an empty board without creating a file or printing initialization messages. The datastore is created only when a mutation actually succeeds.

## Project structure

```text
src/kanban_tui/
  __init__.py
  cli.py
  config.py
  models.py
  rendering.py
  services.py
  storage.py
  transfer.py
  tui.py

tests/
  conftest.py
  test_*.py
```

See [`docs/architecture.md`](docs/architecture.md) for module responsibilities and persistence behavior. See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## Development

Run tests:

```bash
pytest
```

Run coverage:

```bash
pytest --cov=kanban_tui --cov-report=term-missing
```

Lint and verify formatting:

```bash
ruff check .
ruff format --check .
```

Apply formatting:

```bash
ruff format .
```

Run static type checking:

```bash
mypy src/kanban_tui
```

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE).

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues
