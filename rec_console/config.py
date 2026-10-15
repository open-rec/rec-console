"""Deployment mode and feature capabilities exposed to the console UI."""

import os
from pathlib import Path


ALL_FEATURES = (
    "recall", "entities", "serving", "dag", "monitor", "analytics", "airflow", "model",
)
STANDALONE_FEATURES = ("entities", "serving", "monitor")


def data_directory(override=None):
    """Resolve shared state storage, retaining the legacy environment alias."""
    return Path(
        override
        or os.environ.get("REC_CONSOLE_DATA_DIR")
        or os.environ.get("REC_CONSOLE_DATA")
        or "/var/lib/rec-console"
    )


def deployment_mode():
    mode = os.environ.get("OPENREC_MODE", "cluster").strip().lower()
    if mode not in ("cluster", "standalone"):
        raise RuntimeError("OPENREC_MODE must be cluster or standalone")
    return mode


def enabled_features():
    return ALL_FEATURES if deployment_mode() == "cluster" else STANDALONE_FEATURES


def console_config():
    enabled = set(enabled_features())
    return {
        "mode": deployment_mode(),
        "features": {feature: feature in enabled for feature in ALL_FEATURES},
    }
