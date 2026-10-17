"""Shared state directory configuration."""

import os
from pathlib import Path


def data_directory(override=None):
    """Resolve shared state storage, retaining the legacy environment alias."""
    return Path(
        override
        or os.environ.get("REC_CONSOLE_DATA_DIR")
        or os.environ.get("REC_CONSOLE_DATA")
        or "/var/lib/rec-console"
    )
