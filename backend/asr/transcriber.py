# backend/asr/transcriber.py
import numpy as np
from backend.asr.model import get_model
from backend.asr.vad import SileroVAD
from backend.config import settings

SAMPLE_RATE = 16000
OVERLAP_SAMPLES = int(SAMPLE_RATE * 0.4)  # 400ms 重叠窗口，防止切词


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
        self.session_start_ms: float = 0.0

    def reset(self, session_start_ms: float = 0.0):
        self.audio_buffer = np.array([], dtype=np.float32)
        self._buffer_start_s = 0.0
        self.vad.reset()
        self.session_start_ms = session_start_ms

    @property
    def buffer_seconds(self) -> float:
        return len(self.audio_buffer) / SAMPLE_RATE

    @property
    def timestamp_ms(self) -> int:
        """当前缓冲区起始时间（相对于会话开始）"""
        return int((self._buffer_start_s * 1000) - self.session_start_ms)

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

    def transcribe(self) -> str:
        """对当前缓冲区执行 Whisper 推理，返回韩语文本"""
        if len(self.audio_buffer) == 0:
            return ""

        audio = self.audio_buffer.copy()
        segments, _ = self.model.transcribe(
            audio,
            language="ko",
            beam_size=settings.asr_beam_size,
            vad_filter=False,  # 我们自己做 VAD，不用 Whisper 内置的
            condition_on_previous_text=True,
        )
        text = "".join(s.text for s in segments).strip()

        # 过滤幻觉
        if any(w in text for w in settings.hallucination_blacklist) and len(text) < 25:
            return ""

        return text

    def commit(self):
        """最终处理后，保留重叠窗口并重置 VAD 状态"""
        if len(self.audio_buffer) > OVERLAP_SAMPLES:
            self.audio_buffer = self.audio_buffer[-OVERLAP_SAMPLES:]
        else:
            self.audio_buffer = np.array([], dtype=np.float32)
        self._buffer_start_s = len(self.audio_buffer) / SAMPLE_RATE
        self.vad.reset()
