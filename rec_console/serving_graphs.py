"""Versioned publication of the online serving graph."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RecServerError(RuntimeError):
    """Raised when rec-server rejects or cannot serve a graph request."""


class RecServerClient:
    def __init__(self, base_url=None, token=None, timeout=5):
        self.base_url = (base_url or os.environ.get(
            "REC_SERVER_URL", "http://rec-server:13579")).rstrip("/")
        self.token = token or os.environ.get(
            "SERVING_GRAPH_TOKEN", "openrec-serving-graph-token-change-me")
        self.timeout = timeout

    def current(self):
        return self._request("GET", "/internal/serving-graph")

    def activate(self, graph, version):
        return self._request("POST", "/internal/serving-graph", graph, version)

    def _request(self, method, path, body=None, version=None):
        headers = {"Accept": "application/json", "X-OpenRec-Token": self.token}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["X-Graph-Version"] = version
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RecServerError("rec-server rejected serving graph: %s" % detail) from error
        except (URLError, OSError, ValueError) as error:
            raise RecServerError("rec-server serving graph is unavailable: %s" % error) from error
        if isinstance(result, dict) and "status" in result:
            if not result.get("status"):
                raise RecServerError(result.get("msg") or "rec-server rejected serving graph")
            return result.get("data")
        return result


class ServingGraphStore:
    def __init__(self, client=None, data_dir=None):
        self.client = client or RecServerClient()
        root = Path(data_dir or os.environ.get("REC_CONSOLE_DATA_DIR", "/var/lib/rec-console"))
        self.root = root / "serving_graph"

    def current(self):
        runtime = self.client.current()
        current_path = self.root / "current.json"
        current = self._read(current_path) if current_path.exists() else {}
        if not current and runtime.get("graph"):
            current = {
                "version": runtime.get("version") or "classpath-default",
                "published_at": runtime.get("loadedAt") or datetime.now(timezone.utc).isoformat(),
                "checksum": runtime.get("checksum"),
                "graph": runtime["graph"],
            }
            self._persist(current)
        return {
            "version": runtime.get("version") or current.get("version"),
            "checksum": runtime.get("checksum"),
            "loaded_at": runtime.get("loadedAt"),
            "graph": runtime.get("graph"),
            "history": self.history(),
        }

    def publish(self, graph):
        validated = self.validate(graph)
        version = datetime.now(timezone.utc).strftime("graph-%Y%m%dT%H%M%S%fZ")
        runtime = self.client.activate(validated, version)
        release = {
            "version": version,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "checksum": runtime.get("checksum") if runtime else None,
            "graph": validated,
        }
        self._persist(release)
        release["history"] = self.history()
        return release

    def rollback(self, version=None):
        current = self._read(self.root / "current.json") if (self.root / "current.json").exists() else {}
        candidates = [item for item in self.history() if item["version"] != current.get("version")]
        target = version or (candidates[0]["version"] if candidates else None)
        path = self.root / "history" / (str(target) + ".json")
        if not target or not path.exists():
            raise ValueError("serving graph rollback target is not retained: %s" % target)
        release = self._read(path)
        runtime = self.client.activate(release["graph"], release["version"])
        if runtime:
            release["checksum"] = runtime.get("checksum")
        release["published_at"] = datetime.now(timezone.utc).isoformat()
        self._write(self.root / "current.json", release)
        release["history"] = self.history()
        return release

    def history(self):
        directory = self.root / "history"
        if not directory.exists():
            return []
        return [self._read(path) for path in sorted(directory.glob("*.json"), reverse=True)[:20]]

    def _persist(self, release):
        self._write(self.root / "history" / (release["version"] + ".json"), release)
        self._write(self.root / "current.json", release)

    @staticmethod
    def validate(graph):
        if not isinstance(graph, dict):
            raise ValueError("serving graph must be a JSON object")
        nodes, edges = graph.get("nodes"), graph.get("edges")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("serving graph nodes must be a non-empty array")
        if not isinstance(edges, list) or not edges:
            raise ValueError("serving graph edges must be a non-empty array")
        names = [node.get("name") for node in nodes if isinstance(node, dict)]
        if len(names) != len(nodes) or any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("serving graph node names must be present and unique")
        for node in nodes:
            if not node.get("clazz") or not isinstance(node.get("open"), bool):
                raise ValueError("each serving graph node requires clazz and boolean open")
            if not isinstance(node.get("timeout"), int) or node["timeout"] <= 0:
                raise ValueError("each serving graph node timeout must be a positive integer")
        known = set(names)
        for edge in edges:
            if not isinstance(edge, dict) or edge.get("from") not in known or edge.get("to") not in known:
                raise ValueError("each serving graph edge must reference existing nodes")
        return graph

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
