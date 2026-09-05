# Shell completion

[Back to README](../README.md) · [Documentation index](README.md)

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
set -l kanban_config_home ~/.config
if set -q XDG_CONFIG_HOME; and test -n "$XDG_CONFIG_HOME"
    set kanban_config_home "$XDG_CONFIG_HOME"
end
mkdir -p "$kanban_config_home/fish/completions"
env _KANBAN_TUI_COMPLETE=fish_source kanban-tui > "$kanban_config_home/fish/completions/kanban-tui.fish"
```

This uses `~/.config` when `XDG_CONFIG_HOME` is unset or empty.

Regenerate the completion file after upgrading kanbanTUI if the command surface changes.

