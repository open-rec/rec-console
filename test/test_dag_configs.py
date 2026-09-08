import json

import pytest

from rec_console.dag_configs import (DagConfigStore, DEFAULT_DAILY_RECALL,
                                     DEFAULT_DAILY_USER_RECALL)


def test_publish_and_rollback_versioned_daily_config(tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published")
    first = store.publish(DEFAULT_DAILY_RECALL)
    changed = dict(DEFAULT_DAILY_RECALL, schedule="30 3 * * *", algorithms=["hot", "item_cf_i2i"])
    second = store.publish(changed)
    assert store.current()["version"] == second["version"]
    assert json.loads((tmp_path / "published" / "openrec_daily_recall.json").read_text()) \
        ["schedule"] == "30 3 * * *"
    rolled_back = store.rollback()
    assert rolled_back["version"] == first["version"]
    assert store.current()["config"]["algorithms"] == [
        "hot", "new", "item_cf_i2i", "content_i2i", "user_cf_u2i", "item_seq_emb"]


@pytest.mark.parametrize("change", [
    {"schedule": "not-cron"}, {"algorithms": []}, {"algorithms": ["unknown"]},
    {"default_revision": "1"}, {"max_index_versions": 1}, {"retries": 11},
])
def test_rejects_invalid_daily_config(change, tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published")
    with pytest.raises(ValueError):
        store.publish(dict(DEFAULT_DAILY_RECALL, **change))


def test_user_recall_config_has_independent_version_and_publish_file(tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published",
                           "openrec_daily_user_recall")
    release = store.publish(DEFAULT_DAILY_USER_RECALL)
    assert store.current()["version"] == release["version"]
    published = json.loads((tmp_path / "published" /
                            "openrec_daily_user_recall.json").read_text())
    assert published["algorithms"] == ["user_cf_u2u", "content_u2u", "user_emb_u2u"]


def test_user_recall_config_rejects_item_algorithms(tmp_path):
    store = DagConfigStore(tmp_path / "data", tmp_path / "published",
                           "openrec_daily_user_recall")
    with pytest.raises(ValueError):
        store.publish(dict(DEFAULT_DAILY_USER_RECALL, algorithms=["item_cf_i2i"]))
