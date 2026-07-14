"""Run the local application or an isolated, offline demonstration."""

import argparse

import uvicorn

from app.config import BASE_DIR, Settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description="Reporting Mensuel")
    parser.add_argument("--demo", action="store_true", help="Isolated demo without Gemini")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    config = Settings()
    if args.demo:
        config = Settings(
            _env_file=None,
            gemini_api_key="",
            data_dir=BASE_DIR / "data" / "demo",
            reports_dir=BASE_DIR / "reports" / "demo",
            uploads_dir=BASE_DIR / "uploads" / "demo",
        )
    uvicorn.run(create_app(config), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
