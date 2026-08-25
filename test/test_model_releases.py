import json
import hashlib

from rec_console.model_releases import ModelReleaseStore


class FakeStore(ModelReleaseStore):
    def _load(self, scene, manifest):
        return {"path": "%s/%s" % (scene, manifest["version"]), "dim": 7}


def artifact(root, scene, version, passed=True):
    path = root / scene / version
    path.mkdir(parents=True)
    (path / "lr.pth").write_bytes(b"model")
    feature = {"version": 1, "model_type": "lr", "input_dim": 7,
               "user": [], "item": []}
    feature_bytes = json.dumps(feature).encode()
    (path / "lr.features.json").write_bytes(feature_bytes)
    manifest = {"scene": scene, "version": version, "model_type": "lr",
                "model": "lr.pth", "feature": "lr.features.json",
                "input_dim": 7, "feature_sha256": hashlib.sha256(feature_bytes).hexdigest(),
                "metrics": {"auc": .7}, "gate": {"passed": passed}}
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_publish_and_rollback_retained_model(tmp_path):
    artifacts, data = tmp_path / "artifacts", tmp_path / "data"
    artifact(artifacts, "home", "20260820-r001")
    artifact(artifacts, "home", "20260821-r001")
    store = FakeStore(artifacts, data)
    assert store.publish("home", "20260821-r001")["active_version"] == "20260821-r001"
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
    (root / "home" / "bad" / "lr.features.json").write_text("{}")
    store = FakeStore(root, tmp_path / "data")
    try:
        store.publish("home", "bad")
        assert False
    except ValueError as error:
        assert "checksum" in str(error)
