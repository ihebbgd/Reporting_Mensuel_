import asyncio
import re
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse

from app.config import BASE_DIR
from app.models.schemas import (
    KPIResult,
    ReportDetail,
    ReportList,
    ReportSummary,
    TaskRecord,
    TaskStatus,
    TaskStatusResponse,
    UploadResponse,
)
from app.security import authorize
from app.services.comparison import compare_exercises
from app.services.data_processor import DataProcessingError, process_csv
from app.services.task_store import QueueFull, UploadRateExceeded

router = APIRouter(dependencies=[Depends(authorize)])


async def get_record(request, task_id):
    record = await request.app.state.store.get(str(task_id))
    if record is None:
        raise HTTPException(404, "Rapport introuvable.")
    return record


@router.get("/session", tags=["Accès"])
async def session(request: Request):
    config = request.app.state.config
    return {
        "app": config.app_name,
        "ai_available": bool(config.gemini_api_key and config.gemini_api_key != "gemini_key"),
        "max_upload_size_mb": config.max_upload_size_mb,
    }


@router.post("/upload", response_model=UploadResponse, status_code=202, tags=["Rapports"])
async def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    year: int = Form(..., ge=1900, le=2100),
    use_ai: bool = Form(False),
    baseline_id: str = Form(""),
):
    config = request.app.state.config
    filename = re.split(r"[/\\]", file.filename or "")[-1]
    if not filename.lower().endswith(".csv") or len(filename) > 180:
        await file.close()
        raise HTTPException(400, "Sélectionner un fichier CSV (nom de 180 caractères maximum).")
    baseline = None
    if baseline_id:
        previous = await get_record(request, baseline_id)
        if previous.status != TaskStatus.COMPLETED or not previous.result:
            raise HTTPException(409, "Le rapport de référence n'est pas terminé.")
        if previous.year != year - 1:
            raise HTTPException(422, "La référence doit correspondre à l'exercice précédent.")
        baseline = previous.result["kpis"]
    task_id = str(uuid.uuid4())
    path = config.uploads_dir / f"{task_id}.csv"
    accepted = False
    try:
        size = 0
        with path.open("xb") as output:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > config.max_upload_size_mb * 1024 * 1024:
                    raise HTTPException(413, "Fichier trop volumineux.")
                await asyncio.to_thread(output.write, chunk)
        if not size:
            raise HTTPException(422, "Le fichier est vide.")
        await asyncio.to_thread(
            process_csv, str(path), year, config.csv_encoding, config.max_csv_rows
        )
        now = datetime.now(UTC)
        record = TaskRecord(
            task_id=task_id,
            status=TaskStatus.PENDING,
            progress=0,
            created_at=now,
            updated_at=now,
            filename=filename,
            year=year,
            use_ai=use_ai,
            csv_path=str(path),
            baseline=baseline,
        )
        await request.app.state.store.add(
            record, config.max_pending_tasks, config.uploads_per_minute
        )
        accepted = True
        request.app.state.worker.wake.set()
    except DataProcessingError as exc:
        raise HTTPException(422, str(exc)) from None
    except UploadRateExceeded:
        raise HTTPException(
            429,
            "Limite d'imports atteinte. Réessayer dans une minute.",
            headers={"Retry-After": "60"},
        ) from None
    except QueueFull:
        raise HTTPException(
            429,
            "La file de rapports est pleine. Réessayer plus tard.",
            headers={"Retry-After": "60"},
        ) from None
    finally:
        await file.close()
        if not accepted:
            await asyncio.to_thread(path.unlink, missing_ok=True)
    return UploadResponse(task_id=task_id, status=TaskStatus.PENDING, message="Rapport en attente.")


@router.get("/status/{task_id}", response_model=TaskStatusResponse, tags=["Rapports"])
async def get_status(task_id: uuid.UUID, request: Request):
    record = await get_record(request, task_id)
    return TaskStatusResponse(**record.model_dump())


@router.get("/reports", response_model=ReportList, tags=["Rapports"])
async def list_reports(
    request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
):
    records, total = await request.app.state.store.list(limit, offset)
    return ReportList(items=[ReportSummary(**r.model_dump()) for r in records], total=total)


@router.get("/reports/{task_id}", response_model=ReportDetail, tags=["Rapports"])
async def report_detail(task_id: uuid.UUID, request: Request):
    return ReportDetail(**(await get_record(request, task_id)).model_dump())


@router.get("/download/{task_id}", tags=["Rapports"])
async def download_report(task_id: uuid.UUID, request: Request):
    record = await get_record(request, task_id)
    if record.status != TaskStatus.COMPLETED:
        raise HTTPException(409, "Le rapport n'est pas disponible.")
    path = request.app.state.config.reports_dir / f"rapport_{record.year}_{record.task_id}.pdf"
    if not path.is_file():
        raise HTTPException(410, "Le PDF n'est plus disponible.")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.delete("/reports/{task_id}", status_code=204, tags=["Rapports"])
async def delete_report(task_id: uuid.UUID, request: Request):
    record = await get_record(request, task_id)
    if record.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        raise HTTPException(409, "Attendre la fin du traitement avant suppression.")
    path = request.app.state.config.reports_dir / f"rapport_{record.year}_{record.task_id}.pdf"
    await asyncio.to_thread(path.unlink, missing_ok=True)
    await request.app.state.store.delete(record.task_id)
    return Response(status_code=204)


@router.get("/compare", tags=["Rapports"])
async def comparison(request: Request, current_id: uuid.UUID, previous_id: uuid.UUID):
    current, previous = (
        await get_record(request, current_id),
        await get_record(request, previous_id),
    )
    if any(r.status != TaskStatus.COMPLETED or not r.result for r in (current, previous)):
        raise HTTPException(409, "Les deux rapports doivent être terminés.")
    try:
        return compare_exercises(
            KPIResult.model_validate(current.result["kpis"]),
            KPIResult.model_validate(previous.result["kpis"]),
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/examples/{year}", tags=["Exemples"])
def example_csv(year: int):
    if year not in (2024, 2025):
        raise HTTPException(404, "Exemple introuvable.")
    path = BASE_DIR / "examples" / f"demo_{year}.csv"
    return FileResponse(path, media_type="text/csv", filename=path.name)
