from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field

from app.domain.models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")


class Settings(StrictModel):
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_realtime_model: str = "gpt-realtime-2"
    openai_transcription_model: str = "gpt-4o-transcribe"
    openai_voice: Literal["marin", "cedar"] = "marin"
    openai_voice_speed: float = Field(default=1.0, ge=0.25, le=1.5)
    openai_input_noise_reduction: Literal["near_field", "far_field"] = "far_field"

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            openai_realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2"),
            openai_transcription_model=os.getenv(
                "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe"
            ),
            openai_voice=os.getenv("OPENAI_VOICE", "marin"),
            openai_voice_speed=os.getenv("OPENAI_VOICE_SPEED", "1.0"),
            openai_input_noise_reduction=os.getenv("OPENAI_INPUT_NOISE_REDUCTION", "far_field"),
        )
