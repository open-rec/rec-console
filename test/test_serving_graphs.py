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

    def current(self):
        return {"version": self.version, "checksum": "initial", "loadedAt": None,
                "graph": self.graph}

    def activate(self, graph, version):
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
