import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock

from app.api.routes import router
from app.config import BASE_DIR, Settings, settings
from app.security import AccessMiddleware
from app.services.pipeline import ReportWorker
from app.services.task_store import SQLiteTaskStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(config: Settings | None = None, start_worker: bool = True) -> FastAPI:
    config = config or settings

    @asynccontextmanager
    async def lifespan(app):
        for folder in (config.data_dir, config.reports_dir, config.uploads_dir):
            folder.mkdir(parents=True, exist_ok=True)
        # Explicitly reject multiple processes sharing the single-worker demo database.
        lock = FileLock(config.data_dir / "server.lock", timeout=0)
        with lock:
            key_path = config.data_dir / "access.key"
            if config.api_access_key:
                access_key = config.api_access_key
            else:
                if not key_path.exists():
                    key_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
                    key_path.chmod(0o600)
                access_key = key_path.read_text(encoding="utf-8").strip()
            if len(access_key) < 24:
                raise RuntimeError("API_ACCESS_KEY doit contenir au moins 24 caractères.")
            app.state.access_key = access_key
            app.state.config = config
            app.state.store = SQLiteTaskStore(config.data_dir / "reporting.sqlite3")
            await app.state.store.initialize()
            await app.state.store.recover()
            app.state.worker = ReportWorker(app.state.store, config)
            worker_task = asyncio.create_task(app.state.worker.run()) if start_worker else None
            try:
                yield
            finally:
                app.state.worker.stop()
                if worker_task:
                    await worker_task

    app = FastAPI(title="Reporting Mensuel", version="1.0.0", lifespan=lifespan, debug=False)
    app.add_middleware(AccessMiddleware, config=config)
    if config.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(router)
    app.mount(
        "/assets",
        StaticFiles(directory=BASE_DIR / "app" / "static", check_dir=False),
        name="assets",
    )

    @app.get("/health", tags=["System"])
    async def health():
        await app.state.store.list(limit=1)
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(BASE_DIR / "app" / "static" / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port)
