"""Shared warnings for compatibility APIs scheduled for removal."""

import warnings

LEGACY_API_REMOVAL_VERSION = "1.0.0"


def warn_legacy_api(symbol: str, replacement: str, *, stacklevel: int = 2) -> None:
    """Warn that a compatibility symbol will leave the public Python API."""
    warnings.warn(
        f"{symbol} is deprecated; use {replacement}. "
        f"It will be removed in kanbanTUI {LEGACY_API_REMOVAL_VERSION}.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )
