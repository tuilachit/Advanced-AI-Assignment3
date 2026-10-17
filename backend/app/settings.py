from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from app.domain.models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")


class Settings(StrictModel):
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-small"

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
        )
