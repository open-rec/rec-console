from rec_console.config import ALL_FEATURES, console_config


def test_cluster_enables_every_feature(monkeypatch):
    monkeypatch.setenv("OPENREC_MODE", "cluster")
    config = console_config()
    assert config["mode"] == "cluster"
    assert all(config["features"][feature] for feature in ALL_FEATURES)


def test_standalone_only_enables_operational_features(monkeypatch):
    monkeypatch.setenv("OPENREC_MODE", "standalone")
    config = console_config()
    assert {name for name, enabled in config["features"].items() if enabled} == {
        "entities", "serving", "monitor",
    }


def test_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("OPENREC_MODE", "desktop")
    try:
        console_config()
        assert False
    except RuntimeError as error:
        assert "OPENREC_MODE" in str(error)
