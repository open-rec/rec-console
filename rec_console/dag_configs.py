"""Versioned structured configuration for OpenRec DAG templates."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DAILY_RECALL = {
    "schedule": "0 2 * * *",
    "algorithms": ["hot", "new", "item_cf_i2i", "content_i2i", "user_cf_u2i", "item_seq_emb"],
    "default_revision": "r001",
    "max_index_versions": 2,
    "retries": 1,
    "retry_delay_minutes": 5,
}
DEFAULT_DAILY_USER_RECALL = {
    "schedule": "30 2 * * *",
    "algorithms": ["user_cf_u2u", "content_u2u", "user_emb_u2u"],
    "default_revision": "r001", "max_index_versions": 2,
    "retries": 1, "retry_delay_minutes": 5,
}
DEFAULTS = {"openrec_daily_recall": DEFAULT_DAILY_RECALL,
            "openrec_daily_user_recall": DEFAULT_DAILY_USER_RECALL}
ALGORITHMS = {
    "openrec_daily_recall": ("hot", "new", "item_cf_i2i", "content_i2i",
                             "user_cf_u2i", "item_seq_emb"),
    "openrec_daily_user_recall": ("user_cf_u2u", "content_u2u", "user_emb_u2u"),
}


class DagConfigStore:
    def __init__(self, data_dir=None, publish_dir=None, dag_id="openrec_daily_recall"):
        if dag_id not in DEFAULTS:
            raise ValueError("unsupported configurable DAG: %s" % dag_id)
        self.dag_id = dag_id
        self.default = DEFAULTS[dag_id]
        self.data_dir = Path(data_dir or os.environ.get(
            "REC_CONSOLE_DATA_DIR", "/var/lib/rec-console"))
        self.publish_dir = Path(publish_dir or os.environ.get(
            "DAG_CONFIG_DIR", "/opt/openrec/dag-config"))

    def current(self):
        path = self.data_dir / self.dag_id / "current.json"
        if not path.exists():
            return {"version": None, "config": dict(self.default), "history": []}
        result = self._read(path)
        result["history"] = self.history()
        return result

    def publish(self, config):
        validated = self.validate(config, self.dag_id)
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        release = {"version": version, "published_at": datetime.now(timezone.utc).isoformat(),
                   "config": validated}
        history_dir = self.data_dir / self.dag_id / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        self._write(history_dir / (version + ".json"), release)
        self._write(self.data_dir / self.dag_id / "current.json", release)
        self._write(self.publish_dir / (self.dag_id + ".json"), validated)
        release["history"] = self.history()
        return release

    def rollback(self, version=None):
        history = self.history()
        current = self.current().get("version")
        candidates = [item for item in history if item["version"] != current]
        target = version or (candidates[0]["version"] if candidates else None)
        path = self.data_dir / self.dag_id / "history" / (str(target) + ".json")
        if not target or not path.exists():
            raise ValueError("DAG config rollback target is not retained: %s" % target)
        release = self._read(path)
        self._write(self.data_dir / self.dag_id / "current.json", release)
        self._write(self.publish_dir / (self.dag_id + ".json"), release["config"])
        release["history"] = self.history()
        return release

    def history(self):
        directory = self.data_dir / self.dag_id / "history"
        if not directory.exists():
            return []
        return [self._read(path) for path in sorted(directory.glob("*.json"), reverse=True)[:20]]

    @staticmethod
    def validate(config, dag_id="openrec_daily_recall"):
        result = dict(DEFAULTS[dag_id])
        result.update(config or {})
        cron = str(result["schedule"]).split()
        if len(cron) != 5 or any(not re.match(r"^[\d*/?,\-]+$", field) for field in cron):
            raise ValueError("schedule must be a five-field cron expression")
        algorithms = result["algorithms"]
        if not algorithms or len(set(algorithms)) != len(algorithms) \
                or any(item not in ALGORITHMS[dag_id]
                       for item in algorithms):
            raise ValueError("algorithms must be a unique non-empty subset of %s" %
                             ", ".join(ALGORITHMS[dag_id]))
        if not re.match(r"^r\d{3,}$", str(result["default_revision"])):
            raise ValueError("default_revision must look like r001")
        for field, minimum, maximum in (("max_index_versions", 2, 10), ("retries", 0, 10),
                                         ("retry_delay_minutes", 1, 60)):
            value = result[field]
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValueError("%s must be between %d and %d" % (field, minimum, maximum))
        return result

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as source:
            return json.load(source)

    @staticmethod
    def _write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
