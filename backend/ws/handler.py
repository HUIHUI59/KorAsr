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
                            lambda: transcribe_audio(audio, fast=True, initial_prompt=context if context else None)
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
                            lambda: transcribe_audio(audio, initial_prompt=context if context else None)
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
