"""All state stores must honor the same deployment directory and legacy alias."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from rec_console.dag_configs import DagConfigStore
from rec_console.model_releases import ModelReleaseStore
from rec_console.recall_indexes import RecallIndexManager
from rec_console.serving_graphs import ServingGraphStore


@pytest.mark.parametrize("canonical,legacy,explicit,expected", [
    (None, None, None, "/var/lib/rec-console"),
    ("current", None, None, "current"),
    (None, "legacy", None, "legacy"),
    ("current", "legacy", None, "current"),
    ("", "legacy", None, "legacy"),
    ("", "", None, "/var/lib/rec-console"),
    ("current", "legacy", "explicit", "explicit"),
])
def test_all_stores_share_directory(monkeypatch, canonical, legacy, explicit, expected):
    for name, value in (("REC_CONSOLE_DATA_DIR", canonical), ("REC_CONSOLE_DATA", legacy)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    root = Path(expected)
    assert DagConfigStore(data_dir=explicit).data_dir == root
    assert ServingGraphStore(client=Mock(), data_dir=explicit).root == root / "serving_graph"
    assert ModelReleaseStore(data_root=explicit).data_root == root / "models"
    assert RecallIndexManager(Mock(), data_root=explicit).data_root == root


def test_legacy_dag_history_remains_readable_after_switching_to_canonical(tmp_path, monkeypatch):
    monkeypatch.delenv("REC_CONSOLE_DATA_DIR", raising=False)
    monkeypatch.setenv("REC_CONSOLE_DATA", str(tmp_path / "state"))
    store = DagConfigStore(publish_dir=tmp_path / "published")
    published = store.publish(store.current()["config"])

    monkeypatch.setenv("REC_CONSOLE_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("REC_CONSOLE_DATA")
    restored = DagConfigStore(publish_dir=tmp_path / "published").current()
    assert restored["version"] == published["version"]
    assert restored["config"] == published["config"]
