import pytest

from rec_console.model_training import ModelTraining
from rec_console.main import ModelTrainingRequest


def test_training_validates_and_forwards_selection_without_publishing(
    monkeypatch,
):
    calls = []
    selection = {"user": ["user.age"], "candidate": ["item.weight"]}
    request = ModelTrainingRequest(
        business_date="2026-09-16",
        revision="r123",
        feature_selection=selection,
    )

    def validate(self, path, payload):
        assert path == "/features/validate"
        assert payload["feature_selection"] == selection
        return selection

    monkeypatch.setattr(ModelTraining, "algorithm_request", validate)
    monkeypatch.setattr(
        "rec_console.model_training.AirflowClient.trigger",
        lambda self, dag, conf: (
            calls.append((dag, conf)) or {"state": "queued"}
        ),
    )
    resumed = []
    monkeypatch.setattr(
        "rec_console.model_training.AirflowClient.update_dag",
        lambda self, dag, paused: resumed.append((dag, paused)),
    )
    result = ModelTraining().submit(request.model_dump(mode="json"))
    assert resumed == [("openrec_rank_model", False)]
    assert result["state"] == "queued"
    assert calls[0][0] == "openrec_rank_model"
    assert calls[0][1]["scene"] == "global"
    assert calls[0][1]["feature_selection"] == selection
    assert "publish" not in calls[0][1]


def test_training_validation_failure_does_not_trigger_airflow(monkeypatch):
    def reject(*args):
        raise ValueError("unsupported feature")

    monkeypatch.setattr(ModelTraining, "algorithm_request", reject)
    monkeypatch.setattr(
        "rec_console.model_training.AirflowClient.trigger",
        lambda *args: pytest.fail("must not trigger"),
    )
    with pytest.raises(ValueError):
        ModelTraining().submit({"feature_selection": {}})


def test_training_rejects_unrecognized_publication_option():
    with pytest.raises(ValueError):
        ModelTrainingRequest(
            business_date="2026-09-16",
            revision="r123",
            feature_selection={},
            publish=True,
        )


def test_training_catalog_uses_offline_gateway(monkeypatch):
    service = ModelTraining()
    calls = []
    monkeypatch.setenv("RANK_ENGINE_URL", "http://offline-rank:8123")
    monkeypatch.setenv("REC_ALGORITHM_URL", "http://offline-runner:8090")
    monkeypatch.setattr(
        service,
        "_request",
        lambda base, path, payload=None: calls.append((base, path)) or {},
    )
    service.catalog()
    assert calls == [("http://offline-runner:8090", "/features")]
