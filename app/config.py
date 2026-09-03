from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_env_file() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file()


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Agency Overlord")
    database_path: str = os.getenv("DATABASE_PATH", str(ROOT / "data" / "agency_overlord.db"))
    demo_mode: bool = os.getenv("DEMO_MODE", "1") == "1"
    allow_live_publish: bool = os.getenv("ALLOW_LIVE_PUBLISH", "0") == "1"
    session_secret: str = os.getenv("SESSION_SECRET", "change-me-before-production")
    setup_token: str = os.getenv("SETUP_TOKEN", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-terra")
    base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")


settings = Settings()
