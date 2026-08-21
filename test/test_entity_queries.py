import json

from rec_console.entity_queries import EntityQueryClient


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self):
        return json.dumps({"status": True, "data": self.value}).encode()


def test_encodes_entity_query_paths(monkeypatch):
    urls = []

    def fake_open(request, timeout):
        urls.append(request.full_url)
        return Response({"id": "user/a"})

    monkeypatch.setattr("rec_console.entity_queries.urlopen", fake_open)
    client = EntityQueryClient("http://rec-server", timeout=2)
    assert client.user("user/a")["id"] == "user/a"
    client.item("item 1")
    client.events("user/a", "home feed", "click")
    assert urls == [
        "http://rec-server/api/query/user/user%2Fa",
        "http://rec-server/api/query/item/item%201",
        "http://rec-server/api/query/event/user%2Fa/home%20feed/click",
    ]
