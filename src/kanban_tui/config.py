import os
from pathlib import Path

import click
import yaml

from .models import AppConfig, Limits


def get_clikan_home() -> Path:
    configured_home = os.environ.get("CLIKAN_HOME")
    home = Path(configured_home).expanduser() if configured_home else Path.home()
    return home.resolve()


def get_config_path(explicit_path: Path | None = None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    return get_clikan_home() / ".clikan.yaml"


def _resolve_data_path(clikan_data: str, config_path: Path) -> Path:
    data_path = Path(clikan_data).expanduser()
    if data_path.is_absolute():
        return data_path
    return (config_path.parent / data_path).resolve()


def validate_config(config, config_path: Path) -> AppConfig:
    if not isinstance(config, dict):
        raise click.ClickException(
            f"Config file {config_path} must contain a YAML mapping."
        )

    clikan_data = config.get("clikan_data")
    if not isinstance(clikan_data, str) or not clikan_data.strip():
        raise click.ClickException(
            f"Config file {config_path} must define a non-empty clikan_data path."
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
        clikan_data=_resolve_data_path(clikan_data, config_path),
        limits=limits,
        repaint=repaint,
    )


def read_config(explicit_path: Path | None = None) -> AppConfig:
    config_path = get_config_path(explicit_path)
    try:
        with config_path.open("r", encoding="utf-8") as stream:
            try:
                config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                raise click.ClickException(
                    f"Config file {config_path} contains invalid YAML: {exc}"
                )
    except OSError as exc:
        raise click.ClickException(
            f"Could not read config file {config_path}: {exc}"
        )

    return validate_config(config, config_path)


def create_default_config(explicit_path: Path | None = None) -> Path:
    config_path = get_config_path(explicit_path)
    data_path = config_path.with_suffix(".dat")
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as outfile:
            yaml.safe_dump(
                {"clikan_data": str(data_path)},
                outfile,
                default_flow_style=False,
            )
    except OSError as exc:
        raise click.ClickException(
            f"Could not write config file {config_path}: {exc}"
        )
    return config_path
