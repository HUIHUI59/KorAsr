# ASR Optimization (Rolling Context + Parameter Tuning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce hallucinations, missed words, and mis-segmentation in real-time Korean ASR by applying tighter Whisper parameters, rolling cross-segment context, and confidence-based filtering.

**Architecture:** Each final Korean segment's text is appended to a rolling context string (capped at ~200 chars) and passed as `initial_prompt` to the next Whisper inference call, giving the model memory across sentence boundaries. Hallucination filtering is strengthened by exposing `compression_ratio_threshold`, `log_prob_threshold`, and `repetition_penalty` via config. VAD silence duration is reduced from 1000 ms to 600 ms so sentence boundaries are detected faster without over-chopping speech.

**Tech Stack:** faster-whisper, Silero VAD, FastAPI/asyncio, pydantic-settings, SQLite/SQLModel

---

## Files

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/config.py` | Add new ASR/VAD tuning params with better defaults |
| Modify | `backend/asr/transcriber.py` | Accept `initial_prompt`, apply new params, add confidence filter |
| Modify | `backend/ws/handler.py` | Maintain `rolling_context` state; pass to all transcribe calls |
| Modify | `.env.example` | Document new env vars, fix Korean initial prompt |

---

## Task 1: Update `backend/config.py` with new parameters

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Replace the Settings class body**

Open `backend/config.py`. Replace the entire file with:

```python
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
    asr_beam_size: int = 5                        # up from 3 — better accuracy, ~same latency on 4090
    asr_initial_prompt: str = "안녕하세요. 다음은 한국어 강의 및 회의 내용입니다."  # Korean prompt → far fewer TV hallucinations
    asr_max_buffer_s: float = 8.0
    asr_min_buffer_s: float = 0.5
    asr_no_speech_threshold: float = 0.6          # was hardcoded 0.7 in transcriber; exposed here
    asr_compression_ratio_threshold: float = 2.2  # discard overly repetitive outputs (hallucination signal)
    asr_log_prob_threshold: float = -1.0           # discard very low-confidence segments
    asr_repetition_penalty: float = 1.1            # penalise repeated tokens at decoder level

    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 600                  # down from 1000 — faster sentence boundary detection
    vad_min_speech_ms: int = 250

    # Union type prevents pydantic-settings from attempting json.loads before the validator
    hallucination_blacklist: Union[List[str], str] = [
        "자막", "시청해주셔서", "구독", "좋아요", "MBC", "SBS", "KBS",
        "기상캐스터", "다음 영상에서 만나요", "시청자 여러분",
        "Korean university lecture", "이것은 한국 대학교",
        "자막 제공", "번역 제공", "cc 자막", "한국어 자막",
        "감사합니다", "안녕하세요", "시청해 주셔서",
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

    database_url: str = "sqlite:///./data/korasr.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

- [ ] **Step 2: Verify the app still imports cleanly**

```bash
cd C:\AI\korAsr
python -c "from backend.config import settings; print('beam_size:', settings.asr_beam_size, '| silence_ms:', settings.vad_min_silence_ms)"
```

Expected output:
```
beam_size: 5 | silence_ms: 600
```

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(asr): expose beam_size=5, compression_ratio, log_prob, repetition_penalty, silence_ms=600 in config"
```

---

## Task 2: Update `backend/asr/transcriber.py` — new params + initial_prompt support

**Files:**
- Modify: `backend/asr/transcriber.py`

- [ ] **Step 1: Replace the file**

```python
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
```

- [ ] **Step 2: Verify the module imports**

```bash
python -c "from backend.asr.transcriber import transcribe_audio; print('transcriber OK')"
```

Expected:
```
[ASR] Loading Whisper large-v3 on cuda...
[ASR] Model loaded successfully
transcriber OK
```

- [ ] **Step 3: Commit**

```bash
git add backend/asr/transcriber.py
git commit -m "feat(asr): add initial_prompt param, temperature fallback, compression/logprob/repetition filters"
```

---

## Task 3: Update `backend/ws/handler.py` — rolling context state

**Files:**
- Modify: `backend/ws/handler.py`

Rolling context logic:
- `rolling_context: str = ""` is a local variable in `handle_ws` (per-session, not shared).
- After each successful final transcription, the new Korean text is appended.
- Context is capped at 200 characters (trimmed from the left) so it stays short and relevant.
- Both interim and final calls receive the current rolling_context as `initial_prompt`.
- The context update happens inside `_process_final` after `ko` is confirmed non-empty.

- [ ] **Step 1: Replace the file**

```python
# backend/ws/handler.py
import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session as DBSession

from backend.asr.transcriber import Transcriber, transcribe_audio
from backend.translation.moonshot import translate
from backend.storage.database import engine
from backend.storage.models import Session as SessionModel, Segment

INTERIM_INTERVAL = 1.2      # seconds between interim attempts
MAX_CONTEXT_CHARS = 200     # rolling prompt is trimmed to this length

# One GPU slot at a time. Interims skip (non-blocking) if GPU is busy.
# Finals always wait — semaphore is released BEFORE translation so the
# next sentence can start transcribing while Moonshot is in flight.
_gpu_sem = asyncio.Semaphore(1)


def _append_context(current: str, new_text: str) -> str:
    """Append new_text to rolling context, trimming to MAX_CONTEXT_CHARS from the left."""
    combined = (current + " " + new_text).strip()
    if len(combined) > MAX_CONTEXT_CHARS:
        # Keep the rightmost MAX_CONTEXT_CHARS characters so the most recent
        # words are always present (trim older text from the left)
        combined = combined[-MAX_CONTEXT_CHARS:]
    return combined


async def handle_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()

    with DBSession(engine) as db:
        session = db.get(SessionModel, session_id)
        if not session:
            await websocket.close(code=4004, reason="Session not found")
            return
        session_start_ms = session.started_at.timestamp() * 1000

    transcriber = Transcriber()
    transcriber.reset(session_start_ms)

    last_interim_time = time.time()
    segment_counter = 0
    current_seg_id: str | None = None
    rolling_context: str = ""   # grows with each confirmed final segment

    print(f"[WS] Session {session_id} connected")

    async def _safe_send(data: dict) -> bool:
        try:
            await websocket.send_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception:
            return False

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.float32)
            result = transcriber.push_chunk(chunk)
            now = time.time()

            # ── Interim ──────────────────────────────────────────────────────
            if result["should_interim"] and (now - last_interim_time) > INTERIM_INTERVAL:
                last_interim_time = now
                if current_seg_id is None:
                    current_seg_id = str(uuid4())
                sid = current_seg_id
                ts = transcriber.timestamp_ms
                temp_audio = transcriber.audio_buffer.copy()
                ctx = rolling_context   # snapshot — do not mutate inside task

                # 1. Show placeholder card immediately — user sees activity at once
                await _safe_send({
                    "id": sid, "status": "interim",
                    "ko": "...", "zh": "识别中...",
                    "timestamp_ms": ts,
                })

                # 2. If GPU is free, update with real content (non-blocking skip if busy)
                async def _update_interim(audio, seg_id, interim_ts, context):
                    if _gpu_sem.locked():
                        return  # GPU busy → keep "..." placeholder, no queue buildup
                    async with _gpu_sem:
                        txt = await asyncio.to_thread(
                            lambda: transcribe_audio(audio, fast=True, initial_prompt=context)
                        )
                    if txt:
                        await _safe_send({
                            "id": seg_id, "status": "interim",
                            "ko": txt + "...", "zh": "识别中...",
                            "timestamp_ms": interim_ts,
                        })

                asyncio.create_task(_update_interim(temp_audio, sid, ts, ctx))

            # ── Final ─────────────────────────────────────────────────────────
            elif result["should_process"]:
                if current_seg_id is None:
                    current_seg_id = str(uuid4())
                final_id = current_seg_id
                current_seg_id = None
                final_audio = transcriber.audio_buffer.copy()
                ts_ms = transcriber.timestamp_ms
                seq = segment_counter
                segment_counter += 1
                transcriber.commit()
                last_interim_time = time.time()
                ctx = rolling_context   # snapshot for this segment's inference

                async def _process_final(audio, seg_id, ts, s_id, seq_num, context):
                    nonlocal rolling_context

                    # Semaphore only wraps Whisper — released before translation
                    # so next sentence can start transcribing concurrently
                    async with _gpu_sem:
                        ko = await asyncio.to_thread(
                            lambda: transcribe_audio(audio, initial_prompt=context)
                        )

                    if not ko:
                        await _safe_send({"id": seg_id, "status": "remove"})
                        return

                    # Update rolling context with confirmed Korean text
                    rolling_context = _append_context(rolling_context, ko)

                    sent = await _safe_send({
                        "id": seg_id, "status": "translating",
                        "ko": ko, "zh": "翻译中...", "timestamp_ms": ts,
                    })
                    if not sent:
                        return

                    zh = await translate(ko)

                    await _safe_send({
                        "id": seg_id, "status": "done",
                        "ko": ko, "zh": zh, "timestamp_ms": ts,
                    })

                    with DBSession(engine) as db:
                        seg = Segment(
                            id=seg_id, session_id=s_id,
                            sequence=seq_num, timestamp_ms=ts,
                            ko_text=ko, zh_text=zh,
                        )
                        db.add(seg)
                        sess = db.get(SessionModel, s_id)
                        if sess:
                            sess.segment_count += 1
                        db.commit()

                asyncio.create_task(_process_final(final_audio, final_id, ts_ms, session_id, seq, ctx))

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id} disconnected")
        _finalize_session(session_id)


def _finalize_session(session_id: str):
    with DBSession(engine) as db:
        sess = db.get(SessionModel, session_id)
        if sess and sess.ended_at is None:
            now = datetime.now(timezone.utc)
            sess.ended_at = now
            if sess.started_at:
                started = sess.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                sess.duration_seconds = int((now - started).total_seconds())
            db.commit()
```

- [ ] **Step 2: Verify the module imports**

```bash
python -c "from backend.ws.handler import handle_ws, _append_context; print(_append_context('이전 문장', '새 문장'))"
```

Expected:
```
이전 문장 새 문장
```

- [ ] **Step 3: Commit**

```bash
git add backend/ws/handler.py
git commit -m "feat(asr): add rolling context — pass last ~200 chars of Korean transcript as Whisper initial_prompt"
```

---

## Task 4: Update `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Replace the file**

```bash
# Moonshot API authentication key — get yours at platform.moonshot.cn
MOONSHOT_API_KEY=sk-your-key-here

# SQLite database path
DATABASE_URL=sqlite:///./data/korasr.db

# ASR model name (large-v3 = best accuracy, medium/small = faster)
ASR_MODEL=large-v3
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16

# Beam size: higher = more accurate, slightly slower. 5 is recommended for 4090.
ASR_BEAM_SIZE=5

# Korean initial prompt — dramatically reduces TV/YouTube hallucinations.
# Change to match your subject, e.g. "이것은 경제학 강의입니다." for economics.
ASR_INITIAL_PROMPT=안녕하세요. 다음은 한국어 강의 및 회의 내용입니다.

# Max seconds of audio to buffer before forcing transcription
ASR_MAX_BUFFER_S=8.0
# Minimum seconds of audio required to attempt transcription
ASR_MIN_BUFFER_S=0.5

# Whisper confidence thresholds (lower = stricter filtering of bad outputs)
ASR_NO_SPEECH_THRESHOLD=0.6
ASR_COMPRESSION_RATIO_THRESHOLD=2.2
ASR_LOG_PROB_THRESHOLD=-1.0
ASR_REPETITION_PENALTY=1.1

# Voice Activity Detection sensitivity (0.0-1.0, higher = stricter)
VAD_THRESHOLD=0.5
# Milliseconds of silence before considering a sentence complete (600 = faster cuts)
VAD_MIN_SILENCE_MS=600
# Minimum milliseconds of speech to consider valid (filters noise)
VAD_MIN_SPEECH_MS=250

# Comma-separated Whisper hallucination patterns to suppress
HALLUCINATION_BLACKLIST=자막,시청해주셔서,구독,좋아요,MBC,SBS,KBS,기상캐스터,다음 영상에서 만나요,시청자 여러분,자막 제공,번역 제공,cc 자막,한국어 자막
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: update .env.example with new ASR params and Korean initial prompt"
```

---

## Task 5: End-to-End Manual Verification

No automated test suite exists for this project. Verify manually.

- [ ] **Step 1: Start the server**

```bash
python start.py
# or: uvicorn server:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Open the UI and test each issue category**

Open `http://localhost:8000` in Chrome. Enable mic and run these scenarios:

| Scenario | What to check |
|----------|--------------|
| Silence for 5s | No text should appear (hallucination check) |
| Say one short phrase | Should appear as one segment, not split |
| Say 3 sentences in a row | Each should flow naturally; later sentences should benefit from earlier context |
| Say a proper noun (e.g. "삼성전자", "서울대학교") | Should be spelled correctly, not garbled |
| Mid-sentence pause (breathe) | Should NOT trigger a premature cut — wait for real silence |

- [ ] **Step 3: Check server logs for any errors**

Look for:
- No `compression_ratio_threshold` warnings
- No `AttributeError` on `seg.avg_logprob`
- `[WS] Session ... connected` appears on connect

- [ ] **Step 4: Final commit if all looks good**

```bash
git add -A
git commit -m "chore: verified ASR optimization e2e — rolling context + param tuning working"
```
