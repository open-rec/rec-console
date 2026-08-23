import pytest

from rec_console.serving_graphs import ServingGraphStore


GRAPH = {
    "nodes": [
        {"name": "source", "clazz": "example.Source", "configClazz": None,
         "open": True, "timeout": 100, "content": {}},
        {"name": "sink", "clazz": "example.Sink", "configClazz": None,
         "open": True, "timeout": 100, "content": {}},
    ],
    "edges": [{"from": "source", "to": "sink"}],
}


class FakeClient:
    def __init__(self):
        self.version = "classpath-default"
        self.graph = GRAPH

    def current(self, experiment=None):
        return {"version": self.version, "checksum": "initial", "loadedAt": None,
                "graph": self.graph}

    def activate(self, graph, version, experiment="default"):
        self.graph, self.version = graph, version
        return {"version": version, "checksum": "checksum-" + version, "graph": graph}


def test_publish_and_rollback_full_graph(tmp_path):
    client = FakeClient()
    store = ServingGraphStore(client, tmp_path)
    assert store.current()["history"][0]["version"] == "classpath-default"
    first = store.publish(GRAPH)
    changed = {**GRAPH, "nodes": [{**GRAPH["nodes"][0], "timeout": 200}, GRAPH["nodes"][1]]}
    second = store.publish(changed)

    assert store.current()["version"] == second["version"]
    rolled_back = store.rollback(first["version"])
    assert rolled_back["version"] == first["version"]
    assert client.graph["nodes"][0]["timeout"] == 100


def test_rejects_invalid_graph(tmp_path):
    store = ServingGraphStore(FakeClient(), tmp_path)
    with pytest.raises(ValueError, match="existing nodes"):
        store.publish({**GRAPH, "edges": [{"from": "source", "to": "missing"}]})


def test_enable_restores_published_experiment_after_runtime_restart(tmp_path):
    class RecoveryClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.experiments = {"default": {"enabled": True}}

        def current(self, experiment=None):
            result = super().current(experiment)
            if experiment is None:
                result["experiments"] = self.experiments
            return result

        def create_experiment(self, name):
            self.experiments[name] = {"enabled": False}

        def set_experiment_enabled(self, name, enabled):
            self.experiments[name]["enabled"] = enabled
            return self.experiments[name]

    client = RecoveryClient()
    store = ServingGraphStore(client, tmp_path)
    client.create_experiment("test1")
    store.publish(GRAPH, "test1")
    client.experiments.pop("test1")  # simulate rec-server restart

    result = store.set_experiment_enabled("test1", True)

    assert result["enabled"] is True
    assert "test1" in client.experiments
