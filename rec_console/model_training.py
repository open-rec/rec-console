"""Training orchestration over registered rank capabilities and Airflow."""

import json
import os
import urllib.error
import urllib.request

from rec_console.airflow_client import AirflowClient


class ModelTraining:
    def rank_request(self, path, payload=None):
        base = os.environ.get("RANK_ENGINE_URL", "http://rank-engine:8123")
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
            raise RuntimeError("rank capability query failed") from error
        except (OSError, ValueError) as error:
            raise RuntimeError(
                "rank capability query failed: %s" % error
            ) from error
        if result.get("code") != 0:
            raise RuntimeError(result.get("message", "rank request failed"))
        return result["data"]

    def catalog(self):
        return self.rank_request("/features")

    def runtime(self):
        return self.rank_request("/health")

    def submit(self, configuration):
        configuration = dict(configuration)
        configuration["feature_selection"] = self.rank_request(
            "/features/validate", configuration
        )
        # This DAG only produces evaluated artifacts. Publication is separate.
        airflow = AirflowClient()
        airflow.update_dag("openrec_rank_model", paused=False)
        return airflow.trigger("openrec_rank_model", configuration)

    def runs(self):
        return AirflowClient().runs("openrec_rank_model", 30)
