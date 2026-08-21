import io
import json
import urllib.error

from rec_console.analytics import AnalyticsClient, AnalyticsError


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_query_caches_spark_result(monkeypatch):
    AnalyticsClient._cache.clear()
    calls = []
    payload = {"status": "success", "analytics": {"summary": {"pv_ctr": .2}}}

    def open_request(request, timeout):
        calls.append(json.loads(request.data))
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    client = AnalyticsClient("http://runner", ttl=300)
    first = client.query("2026-08-20", "2026-08-21", "scene_0")
    second = client.query("2026-08-20", "2026-08-21", "scene_0")
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1


def test_query_surfaces_runner_error(monkeypatch):
    AnalyticsClient._cache.clear()

    def fail(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    try:
        AnalyticsClient("http://runner").query("2026-08-20", "2026-08-21")
        assert False
    except AnalyticsError as error:
        assert "unavailable" in str(error)
