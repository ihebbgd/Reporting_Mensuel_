import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.main import create_app
from app.models.schemas import TaskRecord, TaskStatus
from app.services.ai_analyzer import generate_analysis
from app.services.comparison import compare_exercises
from app.services.data_processor import DataProcessingError, clean_amount, process_csv
from app.services.financial_calculator import calculate_kpis
from app.services.pdf_generator import generate_pdf
from app.services.task_store import SQLiteTaskStore


@pytest.fixture
def client(app_config):
    with TestClient(create_app(app_config, start_worker=False)) as test_client:
        test_client.headers["Authorization"] = "Bearer " + app_config.api_access_key
        yield test_client


def upload(client, demo_csv, **data):
    return client.post(
        "/upload",
        files={"file": ("demo_2024.csv", demo_csv, "text/csv")},
        data={"year": 2024, **data},
    )


def finish(client, task_id):
    async def run():
        record = await client.app.state.store.claim()
        assert record.task_id == task_id
        await client.app.state.worker.run_one(record)

    client.portal.call(run)


@pytest.mark.parametrize("value", ["nan", "NaN", "Infinity", "-inf", "abc", "1e100"])
def test_invalid_amounts_are_rejected(value):
    with pytest.raises(DataProcessingError):
        clean_amount(value)


@pytest.mark.parametrize(
    ("value", "expected"), [("1.234,56", 1234.56), ("1,234.56", 1234.56), ("1\u202f234,5", 1234.5)]
)
def test_localized_amounts(value, expected):
    assert clean_amount(value) == expected


def test_bad_total_is_not_silently_corrected(tmp_path, demo_csv):
    path = tmp_path / "bad.csv"
    path.write_bytes(demo_csv.replace(b";1200000", b";999"))
    with pytest.raises(DataProcessingError, match="Ligne 2.*Total"):
        process_csv(str(path), year=2024)


def test_explicit_year_ignores_uuid(tmp_path, demo_csv):
    path = tmp_path / "1999-uuid_2024.csv"
    path.write_bytes(demo_csv)
    assert process_csv(str(path), year=2025).annee == 2025


@pytest.mark.parametrize("change", ["nature", "duplicate", "empty", "number", "extra"])
def test_csv_structure_errors(tmp_path, demo_csv, change):
    text = demo_csv.decode("utf-8")
    if change == "nature":
        text = text.replace(";Produit;", ";Inconnu;")
    if change == "duplicate":
        text = text.replace("Libellé", "Compte")
    if change == "empty":
        text = text.splitlines()[0]
    if change == "number":
        text = text.replace(";90000;", ";oops;")
    if change == "extra":
        text = text.replace(";1200000", ";1200000;unexpected")
    path = tmp_path / "input.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DataProcessingError):
        process_csv(str(path))


def test_unauthenticated_requests_never_parse_upload(client):
    response = client.post("/upload", content=b"bad multipart", headers={"Authorization": ""})
    assert response.status_code == 401
    for path in ("/reports", "/session", "/examples/2024"):
        assert client.get(path, headers={"Authorization": ""}).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/").headers["content-security-policy"]


def test_upload_validation_cleanup(client, demo_csv, app_config):
    assert (
        client.post("/upload", files={"file": ("x.exe", demo_csv)}, data={"year": 2024}).status_code
        == 400
    )
    assert upload(client, b"").status_code == 422
    assert upload(client, b"bad csv").status_code == 422
    assert upload(client, demo_csv, year=100).status_code == 422
    assert not list(app_config.uploads_dir.iterdir())


def test_paths_are_uuid_only(client, demo_csv, app_config):
    response = client.post(
        "/upload", files={"file": ("../../evil_2024.csv", demo_csv)}, data={"year": 2024}
    )
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    assert list(app_config.uploads_dir.iterdir()) == [app_config.uploads_dir / (task_id + ".csv")]
    record = client.get("/reports/" + task_id).json()
    assert record["filename"] == "evil_2024.csv"
    assert "csv_path" not in record


def test_upload_and_request_limits(client, app_config):
    app_config.max_upload_size_mb = 1
    response = upload(client, b"x" * (1024 * 1024 + 1))
    assert response.status_code == 413
    response = client.post(
        "/upload", content=b"x", headers={"Content-Length": str(2 * 1024 * 1024)}
    )
    assert response.status_code == 413
    assert not list(app_config.uploads_dir.iterdir())


def test_rate_and_queue_limits(client, demo_csv, app_config):
    app_config.uploads_per_minute = 1
    assert upload(client, demo_csv).status_code == 202
    rejected = upload(client, demo_csv)
    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"
    assert len(list(app_config.uploads_dir.iterdir())) == 1
    app_config.uploads_per_minute = 100
    app_config.max_pending_tasks = 1
    assert upload(client, demo_csv).status_code == 429


def test_pending_download_delete_and_missing(client, demo_csv):
    task_id = upload(client, demo_csv).json()["task_id"]
    assert client.get("/status/" + task_id).json()["status"] == "pending"
    assert client.get("/download/" + task_id).status_code == 409
    assert client.delete("/reports/" + task_id).status_code == 409
    assert client.get("/reports/" + str(uuid4())).status_code == 404
    assert client.get("/status/bad-id").status_code == 422


def test_full_api_pdf_compare_and_delete(client, demo_csv, app_config):
    previous_id = upload(client, demo_csv).json()["task_id"]
    finish(client, previous_id)
    assert client.get("/status/" + previous_id).json()["status"] == "completed"
    current_id = upload(client, demo_csv, year=2025, baseline_id=previous_id).json()["task_id"]
    finish(client, current_id)
    detail = client.get("/reports/" + current_id).json()
    assert detail["result"]["analysis"]["used_model"] == "local"
    assert detail["result"]["comparison"]["previous_year"] == 2024
    response = client.get("/download/" + current_id)
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-type"] == "application/pdf"
    pdf = app_config.reports_dir / f"rapport_2025_{current_id}.pdf"
    document = PdfReader(pdf)
    text = "\n".join(page.extract_text() for page in document.pages)
    assert "2024 / 2025" in text
    assert "non certifié" in text
    comparison = client.get(
        "/compare", params={"previous_id": previous_id, "current_id": current_id}
    )
    assert comparison.json()["indicators"]["ca_annuel"]["difference"] == 0
    assert (
        client.get(
            "/compare", params={"previous_id": current_id, "current_id": previous_id}
        ).status_code
        == 422
    )
    assert client.get("/reports?limit=1").json()["total"] == 2
    assert len(client.get("/reports?limit=1&offset=1").json()["items"]) == 1
    assert not list(app_config.uploads_dir.iterdir())
    assert client.delete("/reports/" + current_id).status_code == 204
    assert not pdf.exists()
    assert client.get("/download/" + current_id).status_code == 404
    assert client.get("/reports").json()["total"] == 1


def test_worker_error_is_sanitized(client, demo_csv):
    task_id = upload(client, demo_csv).json()["task_id"]
    with patch(
        "app.services.pipeline.generate_pdf",
        new=AsyncMock(side_effect=RuntimeError("secret-file-path")),
    ):
        finish(client, task_id)
    record = client.get("/status/" + task_id).json()
    assert record["status"] == "failed"
    assert "secret-file-path" not in record["error"]


def test_store_survives_restart_and_recovers_pending(app_config, demo_csv):
    with TestClient(create_app(app_config, start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer " + app_config.api_access_key
        task_id = upload(client, demo_csv).json()["task_id"]
        client.portal.call(client.app.state.store.claim)
    with TestClient(create_app(app_config, start_worker=False)) as client:
        client.headers["Authorization"] = "Bearer " + app_config.api_access_key
        assert client.get("/status/" + task_id).json()["status"] == "pending"
        assert client.get("/reports").json()["total"] == 1


async def test_store_claim_is_atomic(tmp_path):
    store = SQLiteTaskStore(tmp_path / "test.sqlite3")
    await store.initialize()
    now = datetime.now(UTC)
    record = TaskRecord(
        task_id=str(uuid4()), status=TaskStatus.PENDING, created_at=now, updated_at=now
    )
    await store.add(record, 10, 10)
    claims = await asyncio.gather(store.claim(), store.claim())
    assert sum(item is not None for item in claims) == 1


async def test_ai_timeout_and_opt_out(app_config, demo_csv, tmp_path):
    path = tmp_path / "input.csv"
    path.write_bytes(demo_csv)
    kpis = await calculate_kpis(process_csv(str(path), year=2024))
    app_config.llm_timeout_seconds = 0.01

    async def delayed(**kwargs):
        await asyncio.sleep(1)

    with patch("app.services.ai_analyzer.client") as client:
        client.aio.models.generate_content = AsyncMock(side_effect=delayed)
        result = await generate_analysis(kpis, app_config)
        assert result.is_fallback
        assert client.aio.models.generate_content.call_count == 3
        client.aio.models.generate_content.reset_mock()
        local = await generate_analysis(kpis, app_config, enabled=False)
        assert local.used_model == "local"
        client.aio.models.generate_content.assert_not_called()


async def test_pdf_zero_revenue_and_markup(tmp_path, demo_csv, app_config):
    path = tmp_path / "input.csv"
    path.write_bytes(demo_csv)
    data = process_csv(str(path), year=2024)
    for entry in data.produits:
        entry.montants = {month: 0 for month in entry.montants}
        entry.total = 0
    kpis = await calculate_kpis(data)
    analysis = await generate_analysis(kpis, app_config, enabled=False)
    analysis.resume = "<b>texte non fiable & à vérifier</b>"
    pdf = await generate_pdf(kpis, analysis, str(uuid4()), tmp_path)
    reader = PdfReader(pdf)
    assert len(reader.pages) >= 8
    assert any("<b>texte non fiable" in p.extract_text() for p in reader.pages)
    previous = kpis.model_copy(update={"annee": 2023})
    comparison = compare_exercises(kpis, previous)
    assert comparison["indicators"]["ca_annuel"]["variation_pct"] is None
