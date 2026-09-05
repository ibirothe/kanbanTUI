# kanbanTUI

A terminal-first personal Kanban board for developers. Arch Linux is the primary target environment; the application remains a normal Python CLI/TUI and does not require a daemon, database server, browser, or cloud account.

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

## XDG configuration and data

Fresh Linux installations use the XDG base directories:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/config.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/board.dat
```

Create the default configuration with:

```bash
kanban-tui configure
```

Named boards use separate config and data directories:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/boards/work.yaml
${XDG_DATA_HOME:-~/.local/share}/kanban-tui/boards/work.dat
```

Existing installations are not abandoned: when no XDG config exists, an existing `~/.kanban-tui.yaml` is still discovered. Existing named-board configs under `~/boards/` are also recognized. Fresh configs and named boards use the XDG layout.

`KANBAN_TUI_HOME` remains available as an explicit portable/test override. When set, kanbanTUI keeps config, data, named boards, and custom themes below that directory instead of using XDG paths.

Supported settings:

- `data_path`: datastore path. Relative paths are resolved relative to the configuration file directory.
- `theme`: color theme; default `arch`.
- `limits.todo`: optional TODO capacity.
- `limits.wip`: optional in-progress capacity.
- `limits.done`: maximum completed tasks displayed; default `10`.
- `limits.taskname`: maximum task text length; default `40`.
- `repaint`: display the board after successful mutations; default `false`.

Configuration selection order is:

1. `--config PATH` for an explicit YAML file;
2. `--board NAME` for a named board;
3. `KANBAN_TUI_HOME` when explicitly set;
4. XDG config path;
5. existing legacy `~/.kanban-tui.yaml` when no XDG config exists.

`--config` and `--board` are mutually exclusive.

## Shell completion

Click provides native completion for Bash, Zsh, and Fish. kanbanTUI also completes existing values for `--board` and dynamically discovered theme names.

Generate completion files once rather than invoking kanbanTUI on every shell startup.

### Bash

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui"
_KANBAN_TUI_COMPLETE=bash_source kanban-tui \
  > "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/completion.bash"
printf '%s\n' 'source "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/completion.bash"' >> ~/.bashrc
```

Start a new Bash session after adding the source line.

### Zsh

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui"
_KANBAN_TUI_COMPLETE=zsh_source kanban-tui \
  > "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/completion.zsh"
printf '%s\n' 'source "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/completion.zsh"' >> ~/.zshrc
```

Start a new Zsh session after adding the source line.

### Fish

```fish
mkdir -p "$XDG_CONFIG_HOME/fish/completions"
env _KANBAN_TUI_COMPLETE=fish_source kanban-tui > "$XDG_CONFIG_HOME/fish/completions/kanban-tui.fish"
```

If `XDG_CONFIG_HOME` is unset in Fish, use `~/.config/fish/completions/kanban-tui.fish`.

Regenerate the completion file after upgrading kanbanTUI if the command surface changes.

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
kanban-tui config set theme nord
kanban-tui config set limits.wip 3
kanban-tui config set limits.todo unlimited
kanban-tui config set repaint true
```

The same commands work with `--board` or `--config`:

```bash
kanban-tui --board work config set theme gruvbox
kanban-tui --board work config set limits.wip 2
kanban-tui --config ~/boards/custom.yaml config show
```

Supported `config set` keys are `data_path`, `theme`, `repaint`, `limits.todo`, `limits.wip`, `limits.done`, and `limits.taskname`. Optional TODO/WIP limits accept `unlimited`. Updates are validated before an atomic config-file replacement and preserve unrelated YAML fields.

## Color themes

Themes are stored per selected board/config and apply to both the Rich table output and the Textual TUI. Existing configs without a `theme` field use `arch` automatically.

Built-in themes:

- `arch` — Arch blue on a dark background; default.
- `nord` — muted arctic palette.
- `gruvbox` — warm retro palette.
- `dracula` — high-contrast purple/cyan palette.
- `mono` — neutral grayscale.

Inspect or change the selected board theme:

```bash
kanban-tui theme list
kanban-tui theme current
kanban-tui theme set nord
```

Named boards can use different themes:

```bash
kanban-tui --board work theme set arch
kanban-tui --board personal theme set gruvbox
```

### Custom YAML themes

User themes are discovered automatically from:

```text
${XDG_CONFIG_HOME:-~/.config}/kanban-tui/themes/<name>.yaml
```

When `KANBAN_TUI_HOME` is set, the directory is instead:

```text
$KANBAN_TUI_HOME/themes/<name>.yaml
```

The filename stem is the theme name. Names are lowercase slugs of up to 32 characters containing letters, numbers, `-`, or `_`. Built-in names are reserved and cannot be overridden.

A custom theme inherits from one built-in theme and overrides only the semantic colors you want to change:

```yaml
description: Ocean development theme
extends: arch
colors:
  background: "#101820"
  surface: "#1b2733"
  text: "#e6edf3"
  muted: "#8b98a5"
  accent: "#00aaff"
  todo: "#11bbff"
  wip: "#ffd166"
  done: "#7bd88f"
  priority_low: "#7aa2b8"
  priority_normal: "#00aaff"
  priority_high: "#ffb347"
  priority_urgent: "#ff6b6b"
```

`extends` may be `arch`, `nord`, `gruvbox`, `dracula`, or `mono`; it defaults to `arch`. Every supplied color must use `#RRGGBB`. The supported color roles are exactly those shown above. Unknown keys, unknown roles, invalid YAML, invalid colors, invalid filenames, and attempts to shadow a built-in theme are rejected with an actionable CLI error.

For example:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/themes"
cp examples/theme-custom.yaml \
  "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/themes/ocean.yaml"
kanban-tui theme list
kanban-tui theme set ocean
kanban-tui tui
```

Custom themes are loaded on demand; they do not require reinstalling kanbanTUI. They are global theme definitions, while the selected theme name remains stored independently in each board configuration.

The palette controls TODO/WIP/DONE colors, task metadata badges, TUI chrome, column borders, dialogs, and selection surfaces. Plain and JSON output remain color-free and stable for scripting. Set `NO_COLOR=1` to disable Rich ANSI colors regardless of the selected theme:

```bash
NO_COLOR=1 kanban-tui show
```

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

End-user installation uses pipx. Development should use a project virtual environment rather than Arch's system Python site-packages:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run local checks:

```bash
pytest
pytest --cov=kanban_tui --cov-report=term-missing
ruff check .
ruff format --check .
mypy src/kanban_tui
```

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
  themes.py
  transfer.py
  tui.py

tests/
  conftest.py
  test_*.py
```

See [`docs/architecture.md`](docs/architecture.md) for module responsibilities and persistence behavior. See [`CHANGELOG.md`](CHANGELOG.md) for version history.

## Maintainer

Pascal Rothe  
GitHub: `ibirothe`  
Email: `ibirothe@gmail.com`

## License

MIT. See [`LICENSE`](LICENSE).

## Support

GitHub Issues: https://github.com/ibirothe/kanbanTUI/issues