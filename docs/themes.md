# Color themes

[Back to README](../README.md) · [Documentation index](README.md)

## Color themes

Themes are stored per selected board/config and apply to both the Rich table output and the Textual TUI. Newly created configs and existing configs without a `theme` field use `mono` automatically.

Built-in themes:

- `mono` — Matte Black-inspired grayscale; default.
- `arch` — Tokyo Night-inspired Arch blue.
- `nord` — Omarchy-inspired Nord palette.
- `gruvbox` — Omarchy-inspired Gruvbox palette.
- `dracula` — Omarchy-inspired high-contrast purple palette.

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

`extends` may be `arch`, `nord`, `gruvbox`, `dracula`, or `mono`; it defaults to `mono`. Every supplied color must use `#RRGGBB`. The supported color roles are exactly those shown above, including `selection` and `selection_text` for the active TUI row. Unknown keys, unknown roles, invalid YAML, invalid colors, invalid filenames, and attempts to shadow a built-in theme are rejected with an actionable CLI error.

For example:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/themes"
cp examples/theme-custom.yaml \
  "${XDG_CONFIG_HOME:-$HOME/.config}/kanban-tui/themes/ocean.yaml"
kanban-tui theme list
kanban-tui theme set ocean
kanban-tui tui
```

If a selected custom theme is deleted or becomes invalid, recover with
`kanban-tui theme set arch` or `kanban-tui config set theme arch`. The replacement
configuration is validated before writing and unrelated settings are preserved.

Custom themes are loaded on demand; they do not require reinstalling kanbanTUI. They are global theme definitions, while the selected theme name remains stored independently in each board configuration.

The palette controls TODO/WIP/DONE colors, task metadata badges, TUI chrome, column borders, dialogs, and the high-contrast active-row foreground/background. Plain and JSON output remain color-free and stable for scripting. Set `NO_COLOR=1` to disable Rich ANSI colors regardless of the selected theme:

```bash
NO_COLOR=1 kanban-tui show
```
