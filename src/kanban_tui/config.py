import os
from pathlib import Path

import click
import yaml

from .models import AppConfig, Limits


def get_clikan_home() -> Path:
    configured_home = os.environ.get("CLIKAN_HOME")
    return Path(configured_home).expanduser() if configured_home else Path.home()


def get_config_path() -> Path:
    return get_clikan_home() / ".clikan.yaml"


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
        clikan_data=Path(clikan_data).expanduser(),
        limits=limits,
        repaint=repaint,
    )


def read_config() -> AppConfig:
    config_path = get_config_path()
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


def create_default_config() -> Path:
    home = get_clikan_home()
    config_path = home / ".clikan.yaml"
    data_path = home / ".clikan.dat"
    try:
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
