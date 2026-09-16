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
