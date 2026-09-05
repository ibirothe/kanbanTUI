import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_THEME = "arch"
APP_DIR_NAME = "kanban-tui"
THEME_NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
HEX_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
COLOR_ROLES = (
    "background",
    "surface",
    "text",
    "muted",
    "accent",
    "todo",
    "wip",
    "done",
    "priority_low",
    "priority_normal",
    "priority_high",
    "priority_urgent",
)


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    background: str
    surface: str
    text: str
    muted: str
    accent: str
    todo: str
    wip: str
    done: str
    priority_low: str
    priority_normal: str
    priority_high: str
    priority_urgent: str
    source: str = "builtin"

    def priority_color(self, priority: str) -> str:
        return {
            "low": self.priority_low,
            "normal": self.priority_normal,
            "high": self.priority_high,
            "urgent": self.priority_urgent,
        }[priority]


THEMES: dict[str, Theme] = {
    "arch": Theme(
        name="arch",
        description="Arch blue on a dark terminal-friendly background",
        background="#0f1419",
        surface="#1d252c",
        text="#d8dee9",
        muted="#7f8c98",
        accent="#1793d1",
        todo="#1793d1",
        wip="#f0c674",
        done="#8ec07c",
        priority_low="#6ca6c1",
        priority_normal="#1793d1",
        priority_high="#e5a84b",
        priority_urgent="#ff5f56",
    ),
    "nord": Theme(
        name="nord",
        description="Muted arctic Nord palette",
        background="#2e3440",
        surface="#3b4252",
        text="#eceff4",
        muted="#81a1c1",
        accent="#88c0d0",
        todo="#88c0d0",
        wip="#ebcb8b",
        done="#a3be8c",
        priority_low="#5e81ac",
        priority_normal="#81a1c1",
        priority_high="#d08770",
        priority_urgent="#bf616a",
    ),
    "gruvbox": Theme(
        name="gruvbox",
        description="Warm retro Gruvbox-inspired palette",
        background="#282828",
        surface="#3c3836",
        text="#ebdbb2",
        muted="#928374",
        accent="#d79921",
        todo="#83a598",
        wip="#fabd2f",
        done="#b8bb26",
        priority_low="#8ec07c",
        priority_normal="#d3869b",
        priority_high="#fe8019",
        priority_urgent="#fb4934",
    ),
    "dracula": Theme(
        name="dracula",
        description="High-contrast Dracula-inspired palette",
        background="#282a36",
        surface="#44475a",
        text="#f8f8f2",
        muted="#6272a4",
        accent="#bd93f9",
        todo="#8be9fd",
        wip="#f1fa8c",
        done="#50fa7b",
        priority_low="#6272a4",
        priority_normal="#bd93f9",
        priority_high="#ffb86c",
        priority_urgent="#ff5555",
    ),
    "mono": Theme(
        name="mono",
        description="Neutral grayscale theme",
        background="#111111",
        surface="#262626",
        text="#eeeeee",
        muted="#888888",
        accent="#d0d0d0",
        todo="#c8c8c8",
        wip="#e0e0e0",
        done="#a8a8a8",
        priority_low="#888888",
        priority_normal="#b0b0b0",
        priority_high="#d0d0d0",
        priority_urgent="#ffffff",
    ),
}


def get_user_theme_dir() -> Path:
    """Return the XDG/portable directory containing user theme YAML files."""
    portable_home = os.environ.get("KANBAN_TUI_HOME")
    if portable_home:
        return Path(portable_home).expanduser().resolve() / "themes"

    configured_root = os.environ.get("XDG_CONFIG_HOME")
    config_root = (
        Path(configured_root).expanduser()
        if configured_root
        else Path.home() / ".config"
    )
    return config_root.resolve() / APP_DIR_NAME / "themes"


def _normalize_theme_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("theme name must be a string")
    normalized = name.strip().lower()
    if not THEME_NAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "theme names must be 1-32 lowercase letters/numbers and may contain - or _"
        )
    return normalized


def _custom_theme_paths() -> list[Path]:
    theme_dir = get_user_theme_dir()
    if not theme_dir.exists():
        return []
    if not theme_dir.is_dir():
        raise ValueError(f"custom theme path is not a directory: {theme_dir}")

    paths = sorted(theme_dir.glob("*.yaml"), key=lambda path: path.name.casefold())
    for path in paths:
        name = _normalize_theme_name(path.stem)
        if name in THEMES:
            raise ValueError(
                f"custom theme {path} uses reserved built-in name {name!r}"
            )
    return paths


def _validate_color(role: str, value: object, path: Path) -> str:
    if not isinstance(value, str) or not HEX_COLOR_PATTERN.fullmatch(value.strip()):
        raise ValueError(
            f"custom theme {path}: colors.{role} must be a #RRGGBB color"
        )
    return value.strip().lower()


def _theme_color_mapping(theme: Theme) -> dict[str, str]:
    return {role: getattr(theme, role) for role in COLOR_ROLES}


def _load_custom_theme(path: Path) -> Theme:
    name = _normalize_theme_name(path.stem)
    if name in THEMES:
        raise ValueError(f"custom theme {path} uses reserved built-in name {name!r}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read custom theme {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"custom theme {path} contains invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"custom theme {path} must contain a YAML mapping")

    allowed_keys = {"description", "extends", "colors"}
    unknown_keys = sorted(set(raw) - allowed_keys)
    if unknown_keys:
        keys = ", ".join(str(key) for key in unknown_keys)
        raise ValueError(f"custom theme {path} has unknown keys: {keys}")

    raw_base = raw.get("extends", DEFAULT_THEME)
    if not isinstance(raw_base, str):
        raise ValueError(f"custom theme {path}: extends must be a built-in theme name")
    base_name = _normalize_theme_name(raw_base)
    if base_name not in THEMES:
        choices = ", ".join(THEMES)
        raise ValueError(
            f"custom theme {path}: extends must be one of the built-in themes: {choices}"
        )
    base = THEMES[base_name]

    description = raw.get("description", f"Custom theme based on {base_name}")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"custom theme {path}: description must be a non-empty string")

    raw_colors = raw.get("colors", {})
    if not isinstance(raw_colors, dict):
        raise ValueError(f"custom theme {path}: colors must be a mapping")

    unknown_roles = sorted(set(raw_colors) - set(COLOR_ROLES))
    if unknown_roles:
        roles = ", ".join(str(role) for role in unknown_roles)
        raise ValueError(f"custom theme {path} has unknown color roles: {roles}")

    colors = _theme_color_mapping(base)
    for role, value in raw_colors.items():
        colors[role] = _validate_color(role, value, path)

    return Theme(
        name=name,
        description=description.strip(),
        source="custom",
        **colors,
    )


def theme_names() -> tuple[str, ...]:
    """Return all valid built-in and discovered custom theme names."""
    custom_names: list[str] = []
    for path in _custom_theme_paths():
        theme = _load_custom_theme(path)
        custom_names.append(theme.name)
    return (*THEMES, *custom_names)


def get_theme(name: str) -> Theme:
    """Resolve a built-in or user-defined theme by name."""
    normalized = _normalize_theme_name(name)
    builtin = THEMES.get(normalized)
    if builtin is not None:
        return builtin

    path = get_user_theme_dir() / f"{normalized}.yaml"
    if path.is_file():
        return _load_custom_theme(path)

    choices = ", ".join(theme_names())
    raise ValueError(f"unknown theme {name!r}; choose one of: {choices}")
