import os
import re
import tempfile
from pathlib import Path
from typing import Any

import click
import yaml

from .models import AppConfig, Limits


APP_DIR_NAME = "kanban-tui"
LEGACY_CONFIG_NAME = ".kanban-tui.yaml"
BOARD_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RESERVED_BOARD_NAMES = {"default"}
LIMIT_NAMES = {"todo", "wip", "done", "taskname"}


def _portable_home() -> Path | None:
    configured_home = os.environ.get("KANBAN_TUI_HOME")
    if not configured_home:
        return None
    return Path(configured_home).expanduser().resolve()


def _xdg_root(env_name: str, fallback: Path) -> Path:
    configured = os.environ.get(env_name)
    root = Path(configured).expanduser() if configured else fallback
    return root.resolve()


def get_config_root() -> Path:
    portable = _portable_home()
    if portable is not None:
        return portable
    return _xdg_root("XDG_CONFIG_HOME", Path.home() / ".config") / APP_DIR_NAME


def get_data_root() -> Path:
    portable = _portable_home()
    if portable is not None:
        return portable
    return _xdg_root("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP_DIR_NAME


def get_app_home() -> Path:
    """Return the application root used for portable/legacy callers."""
    return get_config_root()


def get_legacy_config_path() -> Path:
    return (Path.home() / LEGACY_CONFIG_NAME).resolve()


def get_legacy_boards_dir() -> Path:
    return (Path.home() / "boards").resolve()


def get_config_path(explicit_path: Path | None = None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()

    portable = _portable_home()
    if portable is not None:
        return portable / LEGACY_CONFIG_NAME

    xdg_path = get_config_root() / "config.yaml"
    legacy_path = get_legacy_config_path()
    if not xdg_path.exists() and legacy_path.exists():
        return legacy_path
    return xdg_path


def get_default_data_path() -> Path:
    portable = _portable_home()
    if portable is not None:
        return portable / ".kanban-tui.dat"
    return get_data_root() / "board.dat"


def validate_board_name(name: str) -> str:
    normalized = name.strip().lower()
    if not BOARD_NAME_PATTERN.fullmatch(normalized):
        raise click.ClickException(
            "Board names are lowercase slugs containing letters, numbers, '-' or '_'."
        )
    if normalized in RESERVED_BOARD_NAMES:
        raise click.ClickException(f"Board name '{normalized}' is reserved.")
    return normalized


def get_boards_dir() -> Path:
    return get_config_root() / "boards"


def get_board_config_path(name: str) -> Path:
    normalized = validate_board_name(name)
    xdg_path = get_boards_dir() / f"{normalized}.yaml"
    if _portable_home() is not None:
        return xdg_path

    legacy_path = get_legacy_boards_dir() / f"{normalized}.yaml"
    if not xdg_path.exists() and legacy_path.exists():
        return legacy_path
    return xdg_path


def get_board_data_path(name: str) -> Path:
    normalized = validate_board_name(name)
    if _portable_home() is not None:
        return get_boards_dir() / f"{normalized}.dat"
    return get_data_root() / "boards" / f"{normalized}.dat"


def list_named_boards() -> list[str]:
    names: set[str] = set()
    directories = [get_boards_dir()]
    if _portable_home() is None:
        directories.append(get_legacy_boards_dir())

    for boards_dir in directories:
        if not boards_dir.exists():
            continue
        for path in boards_dir.glob("*.yaml"):
            name = path.stem
            if BOARD_NAME_PATTERN.fullmatch(name) and name not in RESERVED_BOARD_NAMES:
                names.add(name)
    return sorted(names)


def _resolve_data_path(raw_path: str, config_path: Path) -> Path:
    data_path = Path(raw_path).expanduser()
    if data_path.is_absolute():
        return data_path.resolve()
    return (config_path.parent / data_path).resolve()


def validate_config(config, config_path: Path) -> AppConfig:
    if not isinstance(config, dict):
        raise click.ClickException(
            f"Config file {config_path} must contain a YAML mapping."
        )

    raw_data_path = config.get("data_path")
    if not isinstance(raw_data_path, str) or not raw_data_path.strip():
        raise click.ClickException(
            f"Config file {config_path} must define a non-empty data_path."
        )

    resolved_config_path = config_path.expanduser().resolve()
    data_path = _resolve_data_path(raw_data_path, resolved_config_path)
    if data_path == resolved_config_path:
        raise click.ClickException(
            f"Config file {resolved_config_path}: data_path must not point to the config file itself."
        )

    try:
        limits = Limits.from_mapping(config.get("limits"))
    except ValueError as exc:
        raise click.ClickException(f"Config file {config_path}: {exc}") from exc

    repaint = config.get("repaint", False)
    if not isinstance(repaint, bool):
        raise click.ClickException(
            f"Config file {config_path}: repaint must be true or false."
        )

    return AppConfig(
        data_path=data_path,
        limits=limits,
        repaint=repaint,
    )


def _read_yaml_document(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Config file {config_path} contains invalid YAML: {exc}"
                ) from exc
    except OSError as exc:
        raise click.ClickException(
            f"Could not read config file {config_path}: {exc}"
        ) from exc

    if not isinstance(config, dict):
        raise click.ClickException(
            f"Config file {config_path} must contain a YAML mapping."
        )
    return config


def read_config_document(explicit_path: Path | None = None) -> dict[str, Any]:
    config_path = get_config_path(explicit_path)
    config = _read_yaml_document(config_path)
    validate_config(config, config_path)
    return config


def read_config(explicit_path: Path | None = None) -> AppConfig:
    config_path = get_config_path(explicit_path)
    return validate_config(_read_yaml_document(config_path), config_path)


def _atomic_write_config(config_path: Path, config: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as outfile:
            yaml.safe_dump(config, outfile, default_flow_style=False, sort_keys=False)
            outfile.flush()
            os.fsync(outfile.fileno())
            temporary_path = Path(outfile.name)
        os.replace(temporary_path, config_path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise click.ClickException(
            f"Could not write config file {config_path}: {exc}"
        ) from exc


def write_config_document(
    config: dict[str, Any], explicit_path: Path | None = None
) -> Path:
    config_path = get_config_path(explicit_path)
    validate_config(config, config_path)
    _atomic_write_config(config_path, config)
    return config_path


def create_default_config(explicit_path: Path | None = None) -> Path:
    config_path = get_config_path(explicit_path)
    if explicit_path is not None or config_path == get_legacy_config_path():
        data_path = config_path.with_suffix(".dat")
    else:
        data_path = get_default_data_path()
    _atomic_write_config(config_path, {"data_path": str(data_path)})
    return config_path


def create_named_board(name: str) -> Path:
    normalized = validate_board_name(name)
    config_path = get_board_config_path(normalized)
    if config_path.exists():
        raise click.ClickException(f"Board '{normalized}' already exists.")
    data_path = get_board_data_path(normalized)
    _atomic_write_config(config_path, {"data_path": str(data_path)})
    return config_path


def set_config_value(
    key: str,
    value: str,
    explicit_path: Path | None = None,
) -> Path:
    config_path = get_config_path(explicit_path)
    config = read_config_document(config_path)
    normalized_key = key.strip().lower()

    if normalized_key == "data_path":
        if not value.strip():
            raise click.ClickException("data_path cannot be empty.")
        config["data_path"] = value.strip()
    elif normalized_key == "repaint":
        normalized_value = value.strip().lower()
        if normalized_value not in {"true", "false"}:
            raise click.ClickException("repaint must be true or false.")
        config["repaint"] = normalized_value == "true"
    elif normalized_key.startswith("limits."):
        limit_name = normalized_key.split(".", 1)[1]
        if limit_name not in LIMIT_NAMES:
            raise click.ClickException(f"Unknown configuration key: {key}")

        limits = config.get("limits")
        if limits is None:
            limits = {}
            config["limits"] = limits
        if not isinstance(limits, dict):
            raise click.ClickException("limits must be a mapping.")

        normalized_value = value.strip().lower()
        if normalized_value in {"none", "null", "unlimited"}:
            if limit_name not in {"todo", "wip"}:
                raise click.ClickException(
                    f"limits.{limit_name} requires a non-negative integer."
                )
            limits.pop(limit_name, None)
        else:
            try:
                parsed = int(value)
            except ValueError as exc:
                raise click.ClickException(
                    f"limits.{limit_name} requires a non-negative integer."
                ) from exc
            if parsed < 0:
                raise click.ClickException(
                    f"limits.{limit_name} requires a non-negative integer."
                )
            limits[limit_name] = parsed
    else:
        raise click.ClickException(f"Unknown configuration key: {key}")

    return write_config_document(config, config_path)
