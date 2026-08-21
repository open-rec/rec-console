import json

import pytest

from rec_console.dag_configs import DagConfigStore, DEFAULT_DAILY_RECALL


def test_publish_and_rollback_versioned_daily_config(tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published")
    first = store.publish(DEFAULT_DAILY_RECALL)
    changed = dict(DEFAULT_DAILY_RECALL, schedule="30 3 * * *", algorithms=["hot", "i2i"])
    second = store.publish(changed)
    assert store.current()["version"] == second["version"]
    assert json.loads((tmp_path / "published" / "openrec_daily_recall.json").read_text()) \
        ["schedule"] == "30 3 * * *"
    rolled_back = store.rollback()
    assert rolled_back["version"] == first["version"]
    assert store.current()["config"]["algorithms"] == ["hot", "new", "i2i", "embedding"]


@pytest.mark.parametrize("change", [
    {"schedule": "not-cron"}, {"algorithms": []}, {"algorithms": ["unknown"]},
    {"default_revision": "1"}, {"max_index_versions": 1}, {"retries": 11},
])
def test_rejects_invalid_daily_config(change, tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published")
    with pytest.raises(ValueError):
        store.publish(dict(DEFAULT_DAILY_RECALL, **change))
