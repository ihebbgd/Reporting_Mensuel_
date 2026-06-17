from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Reporting Mensuel"
    app_version: str = "1.0.0"
    debug: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_access_key: str = Field(default="", repr=False)
    allowed_origins: list[str] = []
    gemini_api_key: str = Field(default="", repr=False)
    llm_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    data_dir: Path = BASE_DIR / "data"
    reports_dir: Path = BASE_DIR / "reports"
    uploads_dir: Path = BASE_DIR / "uploads"
    max_upload_size_mb: int = Field(default=10, ge=1, le=50)
    max_csv_rows: int = Field(default=20000, ge=1, le=100000)
    uploads_per_minute: int = Field(default=5, ge=1)
    max_pending_tasks: int = Field(default=10, ge=1, le=100)
    csv_encoding: str = "utf-8-sig"
    anomaly_threshold_pct: float = Field(default=30, gt=0)
    anomaly_min_active_months: int = Field(default=3, ge=1, le=12)


settings = Settings()
