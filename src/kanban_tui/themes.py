from dataclasses import dataclass


DEFAULT_THEME = "arch"


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


def theme_names() -> tuple[str, ...]:
    return tuple(THEMES)


def get_theme(name: str) -> Theme:
    normalized = name.strip().lower()
    try:
        return THEMES[normalized]
    except KeyError as exc:
        choices = ", ".join(theme_names())
        raise ValueError(f"unknown theme {name!r}; choose one of: {choices}") from exc
