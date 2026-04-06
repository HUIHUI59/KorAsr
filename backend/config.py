# backend/config.py
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List, Union

class Settings(BaseSettings):
    moonshot_api_key: str

    asr_model: str = "large-v3"
    asr_device: str = "cuda"
    asr_compute_type: str = "float16"
    asr_beam_size: int = 5
    asr_max_buffer_s: float = 8.0
    asr_min_buffer_s: float = 0.5

    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 600
    vad_min_speech_ms: int = 250

    # Union type prevents pydantic-settings from attempting json.loads before the validator
    hallucination_blacklist: Union[List[str], str] = [
        "자막", "감사합니다", "시청해주셔서", "구독", "좋아요", "MBC", "SBS", "KBS"
    ]

    @field_validator("hallucination_blacklist", mode="before")
    @classmethod
    def parse_comma_separated(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    model_config = {"env_file": ".env"}

settings = Settings()
