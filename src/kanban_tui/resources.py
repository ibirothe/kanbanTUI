"""Canonical paths and collision checks for one board's file resources."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoardPaths:
    data: Path
    lock: Path
    config: Path | None = None

    @property
    def protected(self) -> frozenset[Path]:
        paths = {self.data, self.lock}
        if self.config is not None:
            paths.add(self.config)
        return frozenset(paths)


def resolve_board_paths(data_path: Path, config_path: Path | None = None) -> BoardPaths:
    """Resolve aliases and reject collisions before opening or replacing files."""
    data = data_path.expanduser().resolve()
    lock = Path(f"{data}.lock").resolve()
    config = config_path.expanduser().resolve() if config_path is not None else None
    if config == data:
        raise ValueError(f"data_path must not point to the config file itself: {data}")
    if config == lock:
        raise ValueError(
            f"config file and datastore lock must use different paths: {lock}"
        )
    if data == lock:
        raise ValueError(
            f"datastore and datastore lock must use different paths: {data}"
        )
    return BoardPaths(data=data, lock=lock, config=config)
