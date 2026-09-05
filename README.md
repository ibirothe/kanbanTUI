# kanbanTUI

A terminal-first personal Kanban board for developers. Arch Linux is the primary target environment; the application remains a normal Python CLI/TUI and does not require a daemon, database server, browser, or cloud account.

## Quick start

After [installation](#arch-linux-installation):

```bash
kanban-tui configure
kanban-tui add My first task
kanban-tui start 1
kanban-tui tui
```

Use the ID printed by `add` if the board already contains tasks. Run `kanban-tui --help`
for all commands or `kanban-tui COMMAND --help` for command options.

## Arch Linux installation

kanbanTUI is intended to be installed as an isolated command-line application with `pipx`, not into Arch's system Python environment.

Install the Arch packages:

```bash
sudo pacman -S --needed python-pipx git
```

Ensure the pipx application directory is on your `PATH`:

```bash
pipx ensurepath
```

Open a new shell after the first `ensurepath`, then install kanbanTUI directly from this Git repository:

```bash
pipx install "git+https://github.com/ibirothe/kanbanTUI.git"
```

Verify the executable and create the initial configuration:

```bash
kanban-tui --version
kanban-tui configure
kanban-tui tui
```

pipx keeps kanbanTUI and its Python dependencies in an isolated virtual environment and exposes only the `kanban-tui` executable on your user `PATH`.

### Updating

The distribution name is normalized by Python tooling to `kanbantui`:

```bash
pipx upgrade kanbantui
```

Check the managed environment with:

```bash
pipx list
```

### Uninstalling

```bash
pipx uninstall kanbantui
```

## Requirements

- Arch Linux is the primary supported desktop/developer environment.
- Python 3.11 or newer. Current Arch Python 3.14 is within the supported version range.
- A terminal suitable for Textual/Rich applications.

## Configuration and customization

- [Configuration and named boards](docs/configuration.md): paths, migration, settings and board selection.
- [Color themes](docs/themes.md): built-in palettes and custom YAML themes.
- [Shell completion](docs/shell-completion.md): Bash, Zsh and Fish setup.

## Interactive TUI

Launch the full-screen board with:

```bash
kanban-tui tui
```

The TUI uses the same configuration, datastore, validation, capacity limits, ordering rules, metadata, theme, undo, and mutation services as the CLI.

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

Running `kanban-tui` without a subcommand shows the board.

```bash
kanban-tui
kanban-tui show
kanban-tui add Fix login bug
kanban-tui edit 1 Fix login timeout handling
kanban-tui priority 1 urgent
kanban-tui tag add 1 backend
kanban-tui tag remove 1 backend
kanban-tui tag clear 1
kanban-tui theme current
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

`start`, `done`, and `todo` move tasks directly to the requested state. `promote` and `regress` remain available as one-step transition shortcuts.

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

`merge` preserves the current board and appends imported tasks. If an imported ID already exists in active or archived history, that imported task is deterministically assigned a fresh ID and the CLI reports the mapping. Non-conflicting imported IDs remain unchanged. `replace` replaces the selected board and preserves imported IDs exactly.

Both modes validate the complete import and configured TODO/WIP capacities before writing. Imports that produce no effective board changes do not write the datastore or replace the current undo snapshot. A successful mutating import can be reverted with `undo`.

## Board view and filters

The table view renders one task per row, wraps long descriptions, shows TODO/WIP capacity, marks full columns, displays metadata, and provides actionable empty states.

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

- `table` is the default Rich terminal view and uses the selected color theme.
- `plain` emits deterministic tab-separated text without color codes.
- `json` emits structured task data with timezone-aware ISO 8601 timestamps plus priority and tags.

Filters and sorting apply consistently to all three formats. All formats use the configured completed-task display limit. Rich output honors `NO_COLOR`.

## Persistence behavior

Reading a board is side-effect free. If the selected datastore does not exist yet, read-only commands and TUI startup see an empty board without creating a file or printing initialization messages. The datastore is created only when a mutation actually succeeds.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the shared local checks and contribution guidance.
The [documentation index](docs/README.md) links to user references, [architecture](docs/architecture.md)
and [maintenance](docs/maintenance.md). Version history lives in [CHANGELOG.md](CHANGELOG.md).

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE).

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues