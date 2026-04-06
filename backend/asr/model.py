# backend/asr/model.py
import warnings
warnings.filterwarnings("ignore")

from faster_whisper import WhisperModel
from backend.config import settings

_model: WhisperModel | None = None

def get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[ASR] Loading Whisper {settings.asr_model} on {settings.asr_device}...")
        _model = WhisperModel(
            settings.asr_model,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
        )
        print("[ASR] Model loaded successfully")
    return _model
