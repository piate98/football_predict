from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
ENV_PATH = BASE_DIR / ".env"


def _load_dotenv(path: Path) -> None:
    """
    Minimal .env loader (no extra dependencies):
    - Reads KEY=VALUE lines
    - Skips comments/blank lines
    - Does NOT overwrite existing real environment variables
    """
    if not path.exists():
        return

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# Ensure .env is loaded into the process environment BEFORE Settings() is created
_load_dotenv(ENV_PATH)


class Settings(BaseSettings):
    # Explicit env name mapping (works for BOTH styles)
    football_data_token: str = Field(
        default="paste_your_real_token_here",
        validation_alias="FOOTBALL_DATA_TOKEN",
    )

    # DB path absolute (stable)
    db_path: str = str(BASE_DIR / "football.db")

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),          # keep this too (harmless + helpful)
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()