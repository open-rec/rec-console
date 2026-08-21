import json
from unittest.mock import patch

from rec_console.airflow_client import AirflowClient


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


def test_authenticates_and_lists_dags(tmp_path):
    password_file = tmp_path / "passwords.json"
    password_file.write_text('{"admin":"secret"}')
    responses = [Response({"access_token": "token"}), Response({"dags": []})]
    with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
        result = AirflowClient(password_file=str(password_file)).dags()
    assert result == {"dags": []}
    token_request = urlopen.call_args_list[0].args[0]
    assert json.loads(token_request.data) == {"username": "admin", "password": "secret"}
    api_request = urlopen.call_args_list[1].args[0]
    assert api_request.headers["Authorization"] == "Bearer token"


def test_quotes_dag_and_run_identifiers(tmp_path):
    password_file = tmp_path / "passwords.json"
    password_file.write_text('{"admin":"secret"}')
    responses = [Response({"access_token": "token"}), Response({"task_instances": []})]
    with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
        AirflowClient(password_file=str(password_file)).tasks("daily recall", "manual/run")
    assert "/daily%20recall/dagRuns/manual%2Frun/taskInstances" in \
        urlopen.call_args_list[1].args[0].full_url


def test_quotes_dag_identifier_when_loading_definition_tasks(tmp_path):
    password_file = tmp_path / "passwords.json"
    password_file.write_text('{"admin":"secret"}')
    responses = [Response({"access_token": "token"}), Response({"tasks": []})]
    with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
        AirflowClient(password_file=str(password_file)).dag_tasks("daily recall")
    assert "/dags/daily%20recall/tasks?limit=200" in urlopen.call_args_list[1].args[0].full_url
