"""Read-only user, item and event queries through rec-server."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class EntityQueryError(RuntimeError):
    pass


class EntityQueryClient:
    def __init__(self, base_url=None, timeout=5):
        self.base_url = (base_url or os.environ.get(
            "REC_SERVER_URL", "http://rec-server:13579")).rstrip("/")
        self.timeout = timeout

    def user(self, user_id):
        return self._get("/api/query/user/%s" % quote(user_id, safe=""))

    def item(self, item_id):
        return self._get("/api/query/item/%s" % quote(item_id, safe=""))

    def events(self, user_id, scene, event_type):
        return self._get("/api/query/event/%s/%s/%s" % (
            quote(user_id, safe=""), quote(scene, safe=""), quote(event_type, safe="")))

    def _get(self, path):
        try:
            request = Request(self.base_url + path, headers={"Accept": "application/json"})
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise EntityQueryError("rec-server query failed: %s" % detail) from error
        except (URLError, OSError, ValueError) as error:
            raise EntityQueryError("rec-server query is unavailable: %s" % error) from error
        if not isinstance(result, dict) or not result.get("status"):
            raise EntityQueryError(result.get("msg", "invalid rec-server query response")
                                   if isinstance(result, dict) else "invalid rec-server query response")
        return result.get("data")
