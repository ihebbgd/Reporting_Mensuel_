import asyncio
import logging
from datetime import UTC, datetime

from app.models.schemas import AIAnalysis, KPIResult, TaskStatus
from app.services.ai_analyzer import generate_analysis
from app.services.comparison import compare_exercises
from app.services.data_processor import DataProcessingError, process_csv
from app.services.financial_calculator import calculate_kpis
from app.services.pdf_generator import generate_pdf

logger = logging.getLogger(__name__)


class ReportWorker:
    def __init__(self, store, config):
        self.store = store
        self.config = config
        self.wake = asyncio.Event()
        self.stopping = False

    async def save(self, record, **changes):
        for key, value in changes.items():
            setattr(record, key, value)
        record.updated_at = datetime.now(UTC)
        await self.store.set(record.task_id, record)

    async def run_one(self, record):
        csv_path = self.config.uploads_dir / f"{record.task_id}.csv"
        try:
            if record.result:
                kpis = KPIResult.model_validate(record.result["kpis"])
                analysis = AIAnalysis.model_validate(record.result["analysis"])
                warnings = record.result["warnings"]
                comparison = record.result["comparison"]
            else:
                await self.save(record, progress=10)
                data = await asyncio.to_thread(
                    process_csv,
                    str(csv_path),
                    record.year,
                    self.config.csv_encoding,
                    self.config.max_csv_rows,
                )
                await self.save(record, progress=25)
                kpis = await calculate_kpis(data, self.config)
                await self.save(record, progress=40)
                analysis = await generate_analysis(kpis, self.config, enabled=record.use_ai)
                comparison = (
                    compare_exercises(kpis, KPIResult.model_validate(record.baseline))
                    if record.baseline
                    else None
                )
                warnings = data.warnings
                # Persist the expensive AI result before PDF rendering, including on restart.
                await self.save(
                    record,
                    progress=70,
                    result={
                        "kpis": kpis.model_dump(mode="json"),
                        "analysis": analysis.model_dump(mode="json"),
                        "warnings": warnings,
                        "comparison": comparison,
                    },
                )
            path = await generate_pdf(
                kpis, analysis, record.task_id, self.config.reports_dir, comparison, warnings
            )
            await self.save(
                record,
                status=TaskStatus.COMPLETED,
                progress=100,
                report_path=str(path),
                error=None,
                csv_path=None,
            )
        except DataProcessingError as exc:
            await self.save(record, status=TaskStatus.FAILED, error=str(exc), csv_path=None)
        except Exception:
            logger.exception("Report generation failed: %s", record.task_id)
            await self.save(
                record,
                status=TaskStatus.FAILED,
                error="Le rapport n'a pas pu être généré. Relancer l'import ou contacter le responsable.",
                csv_path=None,
            )
        finally:
            if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                await asyncio.to_thread(csv_path.unlink, missing_ok=True)

    async def run(self):
        while not self.stopping:
            try:
                self.wake.clear()
                record = await self.store.claim()
                if record:
                    await self.run_one(record)
                else:
                    try:
                        await asyncio.wait_for(self.wake.wait(), timeout=1)
                    except TimeoutError:
                        pass
            except Exception:
                logger.exception("Worker loop failed; retrying")
                await asyncio.sleep(1)

    def stop(self):
        self.stopping = True
        self.wake.set()
