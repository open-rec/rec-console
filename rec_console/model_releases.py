"""Versioned rank-model activation and rollback control."""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class ModelReleaseStore:
    def __init__(self, artifact_root=None, data_root=None, rank_url=None):
        self.artifact_root = Path(artifact_root or os.environ.get(
            "MODEL_ARTIFACT_ROOT", "/models/releases"))
        self.data_root = Path(data_root or os.environ.get(
            "REC_CONSOLE_DATA", "/var/lib/rec-console")) / "models"
        self.rank_url = (rank_url or os.environ.get("RANK_ENGINE_URL", "http://rank-engine:8123")).rstrip("/")

    def list(self, scene):
        releases = []
        scene_root = self.artifact_root / scene
        for path in sorted(scene_root.glob("*/manifest.json"), reverse=True):
            try:
                releases.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        current = self._read(self.data_root / scene / "current.json")
        return {"scene": scene, "active_version": current.get("version") if current else None,
                "active": current, "releases": releases}

    def publish(self, scene, version):
        manifest = self._manifest(scene, version)
        if not manifest.get("gate", {}).get("passed"):
            raise ValueError("model did not pass its evaluation gate")
        activated = self._load(scene, manifest)
        release = dict(manifest)
        release.update({"status": "active", "activated_at": datetime.now(timezone.utc).isoformat(),
                        "runtime": activated})
        self._write(self.data_root / scene / "current.json", release)
        self._write(self.data_root / scene / "history" / (release["activated_at"].replace(":", "-") + ".json"), release)
        return dict(self.list(scene), activated=release)

    def rollback(self, scene, version=None):
        listing = self.list(scene)
        active = listing["active_version"]
        candidates = [item for item in listing["releases"] if item.get("version") != active]
        target = version or (candidates[0].get("version") if candidates else None)
        if not target:
            raise ValueError("no retained model version is available for rollback")
        return self.publish(scene, target)

    def _manifest(self, scene, version):
        manifest = self._read(self.artifact_root / scene / version / "manifest.json")
        if not manifest or manifest.get("scene") != scene or manifest.get("version") != version:
            raise ValueError("model version is not retained: %s" % version)
        for name in (manifest.get("model"), manifest.get("feature")):
            if not name or not (self.artifact_root / scene / version / name).is_file():
                raise ValueError("model artifact is incomplete: %s" % version)
        return manifest

    def _load(self, scene, manifest):
        version = manifest["version"]
        payload = json.dumps({
            "type": manifest.get("model_type", "lr"),
            "model": "/models/releases/%s/%s/%s" % (scene, version, manifest["model"]),
            "feature": "/models/releases/%s/%s/%s" % (scene, version, manifest["feature"]),
            **({"factor_dim": manifest.get("metrics", {}).get("factor_dim")}
               if manifest.get("model_type") == "fm" else {}),
        }).encode()
        request = urllib.request.Request(self.rank_url + "/model/load", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError("rank-engine model activation failed: %s" % error) from error
        if result.get("status") != "success":
            raise RuntimeError("rank-engine rejected model: %s" % result.get("message"))
        return result.get("data")

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None

    @staticmethod
    def _write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True))
        os.replace(temporary, path)
