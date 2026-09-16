"""Training orchestration over registered rank capabilities and Airflow."""

import json
import os
import urllib.error
import urllib.request

from rec_console.airflow_client import AirflowClient


class ModelTraining:
    def _request(self, base, path, payload=None):
        request = urllib.request.Request(
            base.rstrip("/") + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            if path == "/health" and error.code == 503:
                result = json.load(error)
                if result.get("data") is not None:
                    return result["data"]
                raise RuntimeError("rank health check failed") from error
            if error.code == 422:
                raise ValueError(
                    json.load(error).get("detail", "invalid features")
                ) from error
            raise RuntimeError("service request failed") from error
        except (OSError, ValueError) as error:
            raise RuntimeError("service request failed: %s" % error) from error
        if result.get("code") != 0:
            raise RuntimeError(result.get("message", "rank request failed"))
        return result["data"]

    def algorithm_request(self, path, payload=None):
        base = os.environ.get(
            "REC_ALGORITHM_URL", "http://rec-algorithm-runner:8090"
        )
        return self._request(base, path, payload)

    def catalog(self):
        return self.algorithm_request("/features")

    def runtime(self):
        base = os.environ.get("RANK_ENGINE_URL", "http://rank-engine:8123")
        return self._request(base, "/health")

    def submit(self, configuration):
        configuration = dict(configuration)
        configuration["feature_selection"] = self.algorithm_request(
            "/features/validate", configuration
        )
        # This DAG only produces evaluated artifacts. Publication is separate.
        airflow = AirflowClient()
        airflow.update_dag("openrec_rank_model", paused=False)
        return airflow.trigger("openrec_rank_model", configuration)

    def runs(self):
        return AirflowClient().runs("openrec_rank_model", 30)
