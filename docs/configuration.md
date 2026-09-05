# Configuration and named boards

[Back to README](../README.md) · [Documentation index](README.md)

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

