"""Cached client for Spark-backed business analytics."""

import json
import os
import threading
import time
import urllib.error
import urllib.request


class AnalyticsError(RuntimeError):
    pass


class AnalyticsClient:
    _cache = {}
    _lock = threading.Lock()

    def __init__(self, runner_url=None, ttl=None):
        self.runner_url = (runner_url or os.environ.get(
            "REC_ALGORITHM_URL", "http://rec-algorithm-runner:8090")).rstrip("/")
        self.ttl = int(ttl if ttl is not None else os.environ.get("ANALYTICS_CACHE_SECONDS", "300"))

    def query(self, date_from, date_to, scene="", refresh=False):
        key = (date_from, date_to, scene)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and not refresh and now - cached[0] < self.ttl:
            return dict(cached[1], cached=True)
        payload = json.dumps({"date_from": date_from, "date_to": date_to,
                              "scene": scene}).encode()
        request = urllib.request.Request(
            self.runner_url + "/jobs/analytics", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        with self._lock:
            cached = self._cache.get(key)
            if cached and not refresh and time.monotonic() - cached[0] < self.ttl:
                return dict(cached[1], cached=True)
            try:
                with urllib.request.urlopen(request, timeout=7200) as response:
                    result = json.loads(response.read())
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors="replace")
                raise AnalyticsError("analytics job failed: %s" % detail) from error
            except (urllib.error.URLError, json.JSONDecodeError) as error:
                raise AnalyticsError("analytics runner is unavailable: %s" % error) from error
            analytics = result.get("analytics")
            if result.get("status") != "success" or not analytics:
                raise AnalyticsError("analytics runner returned an invalid result")
            self._cache[key] = (time.monotonic(), analytics)
            return dict(analytics, cached=False)
