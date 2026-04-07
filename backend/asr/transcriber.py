# backend/asr/transcriber.py
import time
import numpy as np
from backend.asr.model import get_model
from backend.asr.vad import SileroVAD
from backend.config import settings

SAMPLE_RATE = 16000
OVERLAP_SAMPLES = int(SAMPLE_RATE * 0.4)  # 400ms 重叠窗口，防止切词


def transcribe_audio(audio: np.ndarray, fast: bool = False, initial_prompt: str = "") -> str:
    """Run Whisper inference on an audio array.

    fast=True  → beam_size=2, temperature=0 (greedy, ~3x faster) — used for interim previews.
    fast=False → beam_size from config, temperature fallback sequence — used for finals.

    initial_prompt is prepended to the decoder context so Whisper remembers what was
    said in previous segments (rolling context from the caller).
    """
    model = get_model()

    prompt = initial_prompt.strip() if initial_prompt else settings.asr_initial_prompt

    segments, _ = model.transcribe(
        audio,
        language="ko",
        beam_size=2 if fast else settings.asr_beam_size,
        temperature=0 if fast else (0, 0.2, 0.4),   # fallback sequence: greedy → low heat → medium
        vad_filter=False,                              # Silero VAD handles segmentation upstream
        condition_on_previous_text=True,
        initial_prompt=prompt,
        no_speech_threshold=settings.asr_no_speech_threshold,
        compression_ratio_threshold=settings.asr_compression_ratio_threshold,
        log_prob_threshold=settings.asr_log_prob_threshold,
        repetition_penalty=settings.asr_repetition_penalty,
    )

    parts = []
    for seg in segments:
        # Skip segments Whisper itself flagged as low-confidence
        # (avg_logprob is per-segment; faster-whisper exposes it on the NamedTuple)
        if hasattr(seg, "avg_logprob") and seg.avg_logprob < settings.asr_log_prob_threshold:
            continue
        parts.append(seg.text)

    text = "".join(parts).strip()

    if any(w in text for w in settings.hallucination_blacklist) and len(text) < 45:
        return ""
    return text


class Transcriber:
    def __init__(self):
        self.model = get_model()
        self.vad = SileroVAD(
            threshold=settings.vad_threshold,
            min_silence_ms=settings.vad_min_silence_ms,
            min_speech_ms=settings.vad_min_speech_ms,
        )
        self.audio_buffer = np.array([], dtype=np.float32)
        self._buffer_start_s: float = 0.0
        self._buffer_wall_start: float = 0.0
        self.session_start_ms: float = 0.0

    def reset(self, session_start_ms: float = 0.0):
        self.audio_buffer = np.array([], dtype=np.float32)
        self._buffer_start_s = 0.0
        self._buffer_wall_start = time.time()
        self.vad.reset()
        self.session_start_ms = session_start_ms

    @property
    def buffer_seconds(self) -> float:
        return len(self.audio_buffer) / SAMPLE_RATE

    @property
    def timestamp_ms(self) -> int:
        """Milliseconds elapsed from session start to when this buffer began accumulating."""
        return max(0, int((self._buffer_wall_start - self.session_start_ms / 1000) * 1000))

    def push_chunk(self, chunk: np.ndarray) -> dict:
        """
        推入一个音频块。返回 {'should_process': bool, 'should_interim': bool, 'speech_prob': float}
        should_process=True  → 调用 transcribe() 获取最终结果
        should_interim=True  → 调用 transcribe() 获取中间结果（不重置缓冲区）
        """
        self.audio_buffer = np.concatenate((self.audio_buffer, chunk))
        vad_result = self.vad.process_chunk(chunk)

        is_forced = self.buffer_seconds >= settings.asr_max_buffer_s
        is_end = vad_result["is_end"] and self.buffer_seconds >= settings.asr_min_buffer_s

        return {
            "should_process": is_end or is_forced,
            "should_interim": not is_end and not is_forced and self.buffer_seconds > settings.asr_min_buffer_s,
            "speech_prob": vad_result["speech_prob"],
        }

    def transcribe(self, initial_prompt: str = "") -> str:
        """对当前缓冲区执行 Whisper 推理，返回韩语文本"""
        if len(self.audio_buffer) == 0:
            return ""
        return transcribe_audio(self.audio_buffer.copy(), initial_prompt=initial_prompt)

    def commit(self):
        """最终处理后，保留重叠窗口并重置 VAD 状态"""
        if len(self.audio_buffer) > OVERLAP_SAMPLES:
            self.audio_buffer = self.audio_buffer[-OVERLAP_SAMPLES:]
        else:
            self.audio_buffer = np.array([], dtype=np.float32)
        self._buffer_start_s = len(self.audio_buffer) / SAMPLE_RATE
        self._buffer_wall_start = time.time()
        self.vad.reset()
