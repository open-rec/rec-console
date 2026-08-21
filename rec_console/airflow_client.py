"""Small authenticated client for the Airflow 3 public REST API."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class AirflowError(RuntimeError):
    pass


class AirflowClient:
    def __init__(self, base_url=None, username=None, password=None, password_file=None):
        self.base_url = (base_url or os.environ.get(
            "AIRFLOW_URL", "http://airflow-api-server:8080")).rstrip("/")
        self.username = username or os.environ.get("AIRFLOW_USERNAME", "admin")
        self.password = password or os.environ.get("AIRFLOW_PASSWORD")
        self.password_file = password_file or os.environ.get(
            "AIRFLOW_PASSWORD_FILE",
            "/opt/airflow-logs/simple_auth_manager_passwords.json.generated",
        )

    def dags(self):
        return self.request("GET", "/api/v2/dags?limit=100&order_by=dag_id")

    def dag(self, dag_id):
        return self.request("GET", "/api/v2/dags/%s" % self._quote(dag_id))

    def dag_tasks(self, dag_id):
        return self.request("GET", "/api/v2/dags/%s/tasks?limit=200" % self._quote(dag_id))

    def reparse(self, dag_id):
        dag = self.dag(dag_id)
        token = dag.get("file_token")
        if not token:
            raise AirflowError("Airflow DAG has no file token: %s" % dag_id)
        return self.request("PUT", "/api/v2/parseDagFile/%s" % self._quote(token))

    def update_dag(self, dag_id, paused):
        return self.request("PATCH", "/api/v2/dags/%s" % self._quote(dag_id),
                            {"is_paused": paused})

    def trigger(self, dag_id, conf=None):
        return self.request("POST", "/api/v2/dags/%s/dagRuns" % self._quote(dag_id),
                            {"conf": conf or {}})

    def runs(self, dag_id, limit=20):
        path = "/api/v2/dags/%s/dagRuns?limit=%d&order_by=-start_date" % (
            self._quote(dag_id), limit)
        return self.request("GET", path)

    def tasks(self, dag_id, run_id):
        path = "/api/v2/dags/%s/dagRuns/%s/taskInstances?limit=200" % (
            self._quote(dag_id), self._quote(run_id))
        return self.request("GET", path)

    def logs(self, dag_id, run_id, task_id, try_number=1):
        path = "/api/v2/dags/%s/dagRuns/%s/taskInstances/%s/logs/%d" % (
            self._quote(dag_id), self._quote(run_id), self._quote(task_id), try_number)
        return self.request("GET", path)

    def request(self, method, path, payload=None):
        token = self._token()
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise AirflowError("Airflow returned HTTP %s: %s" % (error.code, detail)) from error
        except OSError as error:
            raise AirflowError("Airflow is unavailable: %s" % error) from error

    def _token(self):
        password = self.password or self._password_from_file()
        request = urllib.request.Request(
            self.base_url + "/auth/token",
            data=json.dumps({"username": self.username, "password": password}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                token = json.loads(response.read().decode()).get("access_token")
        except (OSError, ValueError) as error:
            raise AirflowError("Airflow authentication failed: %s" % error) from error
        if not token:
            raise AirflowError("Airflow authentication returned no access token")
        return token

    def _password_from_file(self):
        try:
            with open(self.password_file, encoding="utf-8") as source:
                passwords = json.load(source)
            return passwords[self.username]
        except (OSError, KeyError, ValueError) as error:
            raise AirflowError("cannot read Airflow password for %s: %s" %
                               (self.username, error)) from error

    @staticmethod
    def _quote(value):
        return urllib.parse.quote(value, safe="")
