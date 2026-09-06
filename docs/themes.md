# Color themes

[Back to README](../README.md) · [Documentation index](README.md)

## Nord

kanbanTUI ships with the Nord palette. It is the default for newly created configurations and for existing configurations without a `theme` field.

```bash
kanban-tui theme list
kanban-tui theme current
kanban-tui theme set nord
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

A custom theme inherits from Nord and overrides only the semantic colors you want to change:

```yaml
description: Ocean development theme
extends: nord
colors:
  background: "#101820"
  surface: "#1b2733"
  text: "#e6edf3"
  muted: "#8b98a5"
  accent: "#00aaff"
  selection: "#1e3a4c"
  selection_text: "#ffffff"
```

`extends` may only be `nord` and defaults to `nord`. Every supplied color must use `#RRGGBB`. The `selection` and `selection_text` roles control the active TUI row.

The palette controls TODO/WIP/DONE colors, task metadata badges, TUI chrome, column borders, dialogs, and the high-contrast active-row foreground/background. Plain and JSON output remain color-free and stable for scripting. Set `NO_COLOR=1` to disable Rich ANSI colors regardless of the selected theme:

```bash
NO_COLOR=1 kanban-tui show
```
