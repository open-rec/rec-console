"""Versioned rank-model activation and rollback control."""

import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from rec_console.release_lock import release_lock


class ModelReleaseStore:
    def __init__(self, artifact_root=None, data_root=None, rank_url=None):
        self.artifact_root = Path(
            artifact_root
            or os.environ.get("MODEL_ARTIFACT_ROOT", "/models/releases")
        )
        self.data_root = (
            Path(
                data_root
                or os.environ.get("REC_CONSOLE_DATA", "/var/lib/rec-console")
            )
            / "models"
        )
        self.rank_url = (
            rank_url
            or os.environ.get("RANK_ENGINE_URL", "http://rank-engine:8123")
        ).rstrip("/")

    def list(self, scene, target_type="item"):
        self._validate_scope(scene, target_type)
        releases = []
        scene_root = self.artifact_root / target_type / scene
        paths = (
            (self.artifact_root / target_type).glob("*/*/manifest.json")
            if scene == "global"
            else scene_root.glob("*/manifest.json")
        )
        for path in sorted(paths, reverse=True):
            try:
                releases.append(json.loads(path.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        releases.sort(
            key=lambda item: item.get("created_at", item["version"]),
            reverse=True,
        )
        current = self._read(self.data_root / target_type / "current.json")
        return {
            "scene": scene,
            "active_version": current.get("version") if current else None,
            "target_type": target_type,
            "active": current,
            "releases": releases,
        }

    def publish(self, scene, version, target_type="item"):
        self._validate_scope(scene, target_type)
        with release_lock(self.data_root / target_type / "release.lock"):
            return self._publish(scene, version, target_type)

    def _publish(self, scene, version, target_type="item"):
        manifest = self._manifest(scene, version, target_type)
        if not manifest.get("gate", {}).get("passed"):
            raise ValueError("model did not pass its evaluation gate")
        activated = self._load(scene, manifest)
        release = dict(manifest)
        release.update(
            {
                "status": "active",
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "runtime": activated,
            }
        )
        self._write(self.data_root / target_type / "current.json", release)
        self._write(
            self.data_root
            / target_type
            / "history"
            / (release["activated_at"].replace(":", "-") + ".json"),
            release,
        )
        return dict(self.list(scene, target_type), activated=release)

    def rollback(self, scene, version=None, target_type="item"):
        self._validate_scope(scene, target_type)
        with release_lock(self.data_root / target_type / "release.lock"):
            return self._rollback(scene, version, target_type)

    def _rollback(self, scene, version=None, target_type="item"):
        listing = self.list(scene, target_type)
        active = listing["active"] or {}
        candidates = [
            item
            for item in listing["releases"]
            if (item.get("scene"), item.get("version"))
            != (active.get("scene"), active.get("version"))
            and item.get("gate", {}).get("passed")
        ]
        if version:
            candidates = [
                item
                for item in listing["releases"]
                if item.get("version") == version
            ]
            if len(candidates) > 1:
                raise ValueError(
                    "ambiguous version; specify its training scene"
                )
        if not candidates:
            raise ValueError(
                "no retained model version is available for rollback"
            )
        selected = candidates[0]
        return self._publish(
            selected["scene"], selected["version"], target_type
        )

    def _manifest(self, scene, version, target_type="item"):
        self._validate_scope(scene, target_type)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", version):
            raise ValueError("invalid version")
        manifest = self._read(
            self.artifact_root
            / target_type
            / scene
            / version
            / "manifest.json"
        )
        if (
            not manifest
            or manifest.get("scene") != scene
            or manifest.get("version") != version
        ):
            raise ValueError("model version is not retained: %s" % version)
        for name in (manifest.get("model"), manifest.get("feature")):
            if (
                not name
                or Path(name).name != name
                or not (
                    self.artifact_root / target_type / scene / version / name
                ).is_file()
            ):
                raise ValueError("model artifact is incomplete: %s" % version)
        feature_path = (
            self.artifact_root
            / target_type
            / scene
            / version
            / manifest["feature"]
        )
        model_path = (
            self.artifact_root
            / target_type
            / scene
            / version
            / manifest["model"]
        )
        if (
            manifest.get("model_sha256")
            and hashlib.sha256(model_path.read_bytes()).hexdigest()
            != manifest["model_sha256"]
        ):
            raise ValueError("model checkpoint checksum does not match")
        expected_hash = manifest.get("feature_sha256")
        if (
            expected_hash
            and hashlib.sha256(feature_path.read_bytes()).hexdigest()
            != expected_hash
        ):
            raise ValueError(
                "model feature artifact checksum does not match: %s" % version
            )
        try:
            feature_space = json.loads(feature_path.read_text())
        except json.JSONDecodeError as error:
            raise ValueError(
                "model feature artifact is invalid: %s" % version
            ) from error
        expected_dim = manifest.get("input_dim")
        if expected_dim is not None and int(
            feature_space.get("input_dim", -1)
        ) != int(expected_dim):
            raise ValueError(
                "model feature dimension does not match manifest: %s" % version
            )
        if feature_space.get("model_type") and feature_space[
            "model_type"
        ] != manifest.get("model_type"):
            raise ValueError(
                "model feature type does not match manifest: %s" % version
            )
        if manifest.get("target_type", "item") != target_type:
            raise ValueError("model target does not match requested target")
        if feature_space.get("target_type", "item") != target_type:
            raise ValueError(
                "model feature target does not match requested target"
            )
        for field in ("catalog_version", "catalog_sha256"):
            if manifest.get(field) is not None and feature_space.get(
                field
            ) != manifest.get(field):
                raise ValueError(
                    "model %s does not match feature sidecar: %s"
                    % (field, version)
                )
        for field in ("feature_selection", "feature_definitions"):
            if manifest.get(field) is not None and manifest[
                field
            ] != feature_space.get(field):
                raise ValueError(
                    "model %s does not match feature sidecar" % field
                )
        return manifest

    @staticmethod
    def _validate_scope(scene, target_type):
        if target_type not in ("item", "user") or not re.fullmatch(
            r"[A-Za-z0-9_-]+", scene
        ):
            raise ValueError("invalid model scope")

    def _load(self, scene, manifest):
        version = manifest["version"]
        payload = json.dumps(
            {
                "type": manifest.get("model_type", "lr"),
                "model": "/models/releases/%s/%s/%s/%s"
                % (
                    manifest.get("target_type", "item"),
                    scene,
                    version,
                    manifest["model"],
                ),
                "feature": "/models/releases/%s/%s/%s/%s"
                % (
                    manifest.get("target_type", "item"),
                    scene,
                    version,
                    manifest["feature"],
                ),
                **(
                    {
                        "factor_dim": manifest.get("metrics", {}).get(
                            "factor_dim"
                        )
                    }
                    if manifest.get("model_type") == "fm"
                    else {}
                ),
            }
        ).encode()
        request = urllib.request.Request(
            self.rank_url + "/model/load",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read())
        except (urllib.error.URLError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "rank-engine model activation failed: %s" % error
            ) from error
        if result.get("status") != "success":
            raise RuntimeError(
                "rank-engine rejected model: %s" % result.get("message")
            )
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
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
