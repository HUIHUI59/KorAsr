# backend/asr/vad.py
import torch
import numpy as np
import warnings

warnings.filterwarnings("ignore")

FRAME_SIZE = 512  # Silero VAD 要求 16kHz 下每帧 512 个采样点

class SileroVAD:
    def __init__(
        self,
        threshold: float = 0.5,
        min_silence_ms: int = 600,
        min_speech_ms: int = 250,
        sample_rate: int = 16000,
    ):
        self.model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
            verbose=False,
            trust_repo=True,
        )
        self.model.eval()
        self.threshold = threshold
        self.sample_rate = sample_rate
        # 转换为帧数
        self._min_silence_frames = max(1, int(min_silence_ms * sample_rate / 1000 / FRAME_SIZE))
        self._min_speech_frames = max(1, int(min_speech_ms * sample_rate / 1000 / FRAME_SIZE))
        self._silence_frames = 0
        self._speech_frames = 0
        self._in_speech = False

    def reset(self):
        self._silence_frames = 0
        self._speech_frames = 0
        self._in_speech = False
        self.model.reset_states()

    def process_chunk(self, chunk: np.ndarray) -> dict:
        """
        处理一个音频块（任意长度），返回 {'speech_prob': float, 'is_end': bool}
        is_end=True 表示检测到语音结束，可以触发 ASR
        """
        probs = []
        for i in range(0, len(chunk) - FRAME_SIZE + 1, FRAME_SIZE):
            frame = torch.from_numpy(chunk[i : i + FRAME_SIZE])
            with torch.no_grad():
                prob = self.model(frame, self.sample_rate).item()
            probs.append(prob)

        if not probs:
            return {"speech_prob": 0.0, "is_end": False}

        avg_prob = float(np.mean(probs))
        is_speech = avg_prob >= self.threshold

        if is_speech:
            self._speech_frames += len(probs)
            self._silence_frames = 0
            self._in_speech = True
        elif self._in_speech:
            self._silence_frames += len(probs)

        is_end = (
            self._in_speech
            and not is_speech
            and self._silence_frames >= self._min_silence_frames
            and self._speech_frames >= self._min_speech_frames
        )

        return {"speech_prob": avg_prob, "is_end": is_end}
