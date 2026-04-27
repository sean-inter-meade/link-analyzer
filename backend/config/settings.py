from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


INTERCOM_API_TOKEN: str = os.environ.get("INTERCOM_API_TOKEN", "")
INTERCOM_API_BASE: str = os.environ.get(
    "INTERCOM_API_BASE", "https://api.intercom.io"
)

USE_TRANSFORMER: bool = os.environ.get("USE_TRANSFORMER", "false").lower() == "true"

CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
CACHE_MAX_SIZE: int = int(os.environ.get("CACHE_MAX_SIZE", "100"))

RATE_LIMIT_REQUESTS: int = int(os.environ.get("RATE_LIMIT_REQUESTS", "30"))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
