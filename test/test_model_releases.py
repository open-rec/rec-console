import json
import hashlib

from rec_console.model_releases import ModelReleaseStore


class FakeStore(ModelReleaseStore):
    def _load(self, scene, manifest):
        return {"path": "%s/%s" % (scene, manifest["version"]), "dim": 7}


def artifact(root, scene, version, passed=True):
    path = root / "item" / scene / version
    path.mkdir(parents=True)
    (path / "lr.pth").write_bytes(b"model")
    feature = {
        "version": 1,
        "model_type": "lr",
        "input_dim": 7,
        "user": [],
        "item": [],
    }
    feature_bytes = json.dumps(feature).encode()
    (path / "lr.features.json").write_bytes(feature_bytes)
    manifest = {
        "scene": scene,
        "version": version,
        "model_type": "lr",
        "model": "lr.pth",
        "feature": "lr.features.json",
        "input_dim": 7,
        "feature_sha256": hashlib.sha256(feature_bytes).hexdigest(),
        "metrics": {"auc": 0.7},
        "gate": {"passed": passed},
    }
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_publish_and_rollback_retained_model(tmp_path):
    artifacts, data = tmp_path / "artifacts", tmp_path / "data"
    artifact(artifacts, "home", "20260820-r001")
    artifact(artifacts, "home", "20260821-r001")
    store = FakeStore(artifacts, data)
    assert (
        store.publish("home", "20260821-r001")["active_version"]
        == "20260821-r001"
    )
    assert store.rollback("home")["active_version"] == "20260820-r001"


def test_publish_rejects_failed_evaluation(tmp_path):
    artifact(tmp_path / "artifacts", "home", "bad", passed=False)
    store = FakeStore(tmp_path / "artifacts", tmp_path / "data")
    try:
        store.publish("home", "bad")
        assert False
    except ValueError as error:
        assert "evaluation" in str(error)


def test_publish_rejects_tampered_feature_sidecar(tmp_path):
    root = tmp_path / "artifacts"
    artifact(root, "home", "bad")
    (root / "item" / "home" / "bad" / "lr.features.json").write_text("{}")
    store = FakeStore(root, tmp_path / "data")
    try:
        store.publish("home", "bad")
        assert False
    except ValueError as error:
        assert "checksum" in str(error)


def test_publish_rejects_catalog_provenance_mismatch(tmp_path):
    root = tmp_path / "artifacts"
    artifact(root, "home", "bad")
    path = root / "item" / "home" / "bad" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["catalog_version"] = 1
    manifest["catalog_sha256"] = "different"
    path.write_text(json.dumps(manifest))
    store = FakeStore(root, tmp_path / "data")
    try:
        store.publish("home", "bad")
        assert False
    except ValueError as error:
        assert "catalog_version" in str(error) or "catalog_sha256" in str(
            error
        )


def test_publication_is_global_per_target_not_per_training_scene(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifact(artifacts, "home", "v1")
    artifact(artifacts, "search", "v2")
    store = FakeStore(artifacts, tmp_path / "data")
    store.publish("home", "v1")
    store.publish("search", "v2")
    assert store.list("home")["active"]["scene"] == "search"
    assert len(store.list("global")["releases"]) == 2
    assert store.rollback("global")["active_version"] == "v1"


def test_publish_rejects_changed_feature_selection(tmp_path):
    import pytest

    artifact(tmp_path, "global", "v1")
    path = tmp_path / "item/global/v1/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["feature_selection"] = {
        "user": ["user.age"],
        "candidate": ["item.weight"],
    }
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="feature_selection"):
        FakeStore(tmp_path, tmp_path / "data").publish("global", "v1")


def test_global_rollback_distinguishes_same_version_across_scenes(tmp_path):
    import pytest

    artifact(tmp_path, "home", "v1")
    artifact(tmp_path, "search", "v1")
    store = FakeStore(tmp_path, tmp_path / "data")
    store.publish("home", "v1")
    assert store.rollback("global")["active"]["scene"] == "search"
    with pytest.raises(ValueError, match="ambiguous"):
        store.rollback("global", "v1")


def test_publish_cannot_override_features():
    import pytest
    from pydantic import ValidationError
    from rec_console.main import ModelPublishRequest

    with pytest.raises(ValidationError):
        ModelPublishRequest(scene="global", version="v1", feature_selection={})


def test_concurrent_publications_share_lock_across_store_instances(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    root = tmp_path / "artifacts"
    for version in ("v1", "v2"):
        artifact(root, "home", version)
    first_loaded, finish_first, second_started, second_loaded = (Event() for _ in range(4))
    runtime = {}

    class BlockingStore(FakeStore):
        def _load(self, scene, manifest):
            version = manifest["version"]
            runtime["version"] = version
            if version == "v1":
                first_loaded.set()
                assert finish_first.wait(5)
            else:
                second_loaded.set()
            return super()._load(scene, manifest)

    first = BlockingStore(root, tmp_path / "data")
    second = BlockingStore(root, tmp_path / "data")
    def publish_second():
        second_started.set()
        return second.publish("home", "v2")

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(first.publish, "home", "v1")
        try:
            assert first_loaded.wait(5)
            b = executor.submit(publish_second)
            assert second_started.wait(5)
            assert not second_loaded.wait(0.1)
        finally:
            finish_first.set()
        a.result(timeout=5)
        b.result(timeout=5)
    assert runtime["version"] == second.list("home")["active_version"] == "v2"
    assert len(list((tmp_path / "data/models/item/history").glob("*.json"))) == 2


def test_rollback_waits_for_publication_before_selecting_previous(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    root = tmp_path / "artifacts"
    for version in ("v1", "v2"):
        artifact(root, "home", version)
    loaded, finish, rollback_started = Event(), Event(), Event()
    runtime = {}

    class BlockingStore(FakeStore):
        def _load(self, scene, manifest):
            runtime["version"] = manifest["version"]
            if manifest["version"] == "v2":
                loaded.set()
                assert finish.wait(5)
            return super()._load(scene, manifest)

    store = BlockingStore(root, tmp_path / "data")
    store.publish("home", "v1")
    other = BlockingStore(root, tmp_path / "data")
    def rollback():
        rollback_started.set()
        return other.rollback("home")

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(store.publish, "home", "v2")
        try:
            assert loaded.wait(5)
            b = executor.submit(rollback)
            assert rollback_started.wait(5)
        finally:
            finish.set()
        a.result(timeout=5)
        assert b.result(timeout=5)["active_version"] == "v1"
    assert runtime["version"] == store.list("home")["active_version"] == "v1"


def test_atomic_write_failure_preserves_current_and_removes_temporary(tmp_path, monkeypatch):
    import pytest
    import rec_console.model_releases as module

    path = tmp_path / "current.json"
    path.write_text('{"version": "old"}')
    def fail_replace(*args):
        raise OSError("disk error")
    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk error"):
        ModelReleaseStore._write(path, {"version": "new"})
    assert json.loads(path.read_text())["version"] == "old"
    assert list(tmp_path.iterdir()) == [path]
