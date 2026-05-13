from pathlib import Path


class FakeImpactEngine:
    def __init__(self, dashboard):
        self.dashboard = dashboard

    def generate_json_output(self):
        return {
            "map_name": "de_dust2",
            "utility_diagnostics": {"total_he_events": 1},
            "players": [
                {
                    "player_name": "T1",
                    "team": "team2",
                    "rating_0_100": 72.5,
                    "flash_score": 1.0,
                    "smoke_score": 2.0,
                    "fire_score": 3.0,
                    "he_score": 4.0,
                    "utility_impact": 10.0,
                    "utility_event_count": 4,
                    "map_control_score": 0.5,
                    "tactical_discipline_score": 0.2,
                    "utility_stats": {},
                    "flash_events": [],
                    "smoke_events": [],
                    "fire_events": [],
                    "he_events": [],
                    "tactical_events": [],
                }
            ],
        }


class FailingImpactEngine:
    def __init__(self, dashboard):
        self.dashboard = dashboard

    def generate_json_output(self):
        raise RuntimeError("impact failed")


def load_web_app_without_env_leak():
    import importlib
    import os

    previous_utf8 = os.environ.get("PYTHONUTF8")
    previous_io = os.environ.get("PYTHONIOENCODING")
    module = importlib.import_module("demo_analysis.web_app")
    if previous_utf8 is None:
        os.environ.pop("PYTHONUTF8", None)
    else:
        os.environ["PYTHONUTF8"] = previous_utf8
    if previous_io is None:
        os.environ.pop("PYTHONIOENCODING", None)
    else:
        os.environ["PYTHONIOENCODING"] = previous_io
    return module


def test_attach_impact_engine_payload_success(monkeypatch):
    web_app = load_web_app_without_env_leak()
    monkeypatch.setattr(web_app, "ImpactEngine", FakeImpactEngine)
    dashboard = {"rounds": [], "overall": []}

    result = web_app.attach_impact_engine_payload(dashboard)

    assert result["impact_engine"]["map_name"] == "de_dust2"
    assert result["impact_engine"]["players"][0]["flash_score"] == 1.0
    assert "impact_engine_error" not in result


def test_attach_impact_engine_payload_failure(monkeypatch):
    web_app = load_web_app_without_env_leak()
    monkeypatch.setattr(web_app, "ImpactEngine", FailingImpactEngine)
    dashboard = {"rounds": [], "overall": []}

    result = web_app.attach_impact_engine_payload(dashboard)

    assert result["impact_engine"] is None
    assert "impact failed" in result["impact_engine_error"]


def test_analyze_status_returns_impact_engine_dashboard(monkeypatch):
    web_app = load_web_app_without_env_leak()
    dashboard = {"impact_engine": {"players": [{"player_name": "T1"}]}}
    job_id = "impact-job"
    with web_app.ANALYSIS_LOCK:
        web_app.ANALYSIS_JOBS[job_id] = {
            "status": "succeeded",
            "phase": "done",
            "dashboard": dashboard,
            "analysis_id": "abc12345",
            "run_id": "run123",
        }

    try:
        client = web_app.app.test_client()
        response = client.get(f"/api/analyze_status/{job_id}")
        payload = response.get_json()
    finally:
        with web_app.ANALYSIS_LOCK:
            web_app.ANALYSIS_JOBS.pop(job_id, None)

    assert response.status_code == 200
    assert payload["dashboard"]["impact_engine"]["players"][0]["player_name"] == "T1"


def test_frontend_contains_impact_engine_panel_and_columns():
    root = Path(__file__).resolve().parents[3]
    index_html = (root / "demo_analysis" / "templates" / "index.html").read_text(encoding="utf-8")
    app_js = (root / "demo_analysis" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="impact-engine-view"' in index_html
    assert "renderImpactEnginePanel" in app_js
    for field in (
        "flash_score",
        "smoke_score",
        "fire_score",
        "he_score",
        "utility_impact",
        "utility_event_count",
        "map_control_score",
        "tactical_discipline_score",
    ):
        assert field in app_js
