from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def demo_csv():
    return (Path(__file__).resolve().parents[1] / "examples" / "demo_2024.csv").read_bytes()


@pytest.fixture
def app_config(tmp_path):
    return Settings(
        _env_file=None,
        api_access_key="testing-access-key-0123456789",
        gemini_api_key="",
        data_dir=tmp_path / "data",
        reports_dir=tmp_path / "reports",
        uploads_dir=tmp_path / "uploads",
        uploads_per_minute=100,
        max_pending_tasks=20,
    )


@pytest.fixture(autouse=True)
def fast_ai_retries(monkeypatch):
    monkeypatch.setattr("app.services.ai_analyzer.RETRY_DELAY", 0)
