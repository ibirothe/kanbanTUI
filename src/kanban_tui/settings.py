"""Application configuration assembled at adapter entry points."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .policy import BoardPolicy


def _non_negative_integer(value: Any, *, error: str) -> int:
    if isinstance(value, bool):
        raise ValueError(error)
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdecimal():
        parsed = int(value.strip())
    else:
        raise ValueError(error)
    if parsed < 0:
        raise ValueError(error)
    return parsed


@dataclass
class Limits:
    """Compatible config-file representation of domain and display limits."""

    todo: int | None = None
    wip: int | None = None
    done: int = 10
    taskname: int = 40

    @classmethod
    def from_mapping(cls, raw: Any) -> "Limits":
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("limits must be a mapping")

        values: dict[str, int | None] = {
            "todo": None,
            "wip": None,
            "done": 10,
            "taskname": 40,
        }
        for name in values:
            if name not in raw:
                continue
            values[name] = _non_negative_integer(
                raw[name],
                error=f"limits.{name} must be a non-negative integer",
            )

        done, taskname = values["done"], values["taskname"]
        assert done is not None and taskname is not None
        return cls(todo=values["todo"], wip=values["wip"], done=done, taskname=taskname)

    def board_policy(self) -> BoardPolicy:
        return BoardPolicy(
            todo_limit=self.todo,
            wip_limit=self.wip,
            task_text_limit=self.taskname,
        )


@dataclass(frozen=True)
class PresentationSettings:
    """Options consumed only by terminal presentation adapters."""

    done_limit: int = 10
    repaint: bool = False
    theme: str = "nord"


@dataclass
class AppConfig:
    """Compatibility wiring for infrastructure, domain and presentation settings."""

    data_path: Path
    limits: Limits = field(default_factory=Limits)
    repaint: bool = False
    theme: str = "nord"

    @property
    def policy(self) -> BoardPolicy:
        return self.limits.board_policy()

    @property
    def presentation(self) -> PresentationSettings:
        return PresentationSettings(
            done_limit=self.limits.done,
            repaint=self.repaint,
            theme=self.theme,
        )
