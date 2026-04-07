# backend/ws/handler.py
import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session as DBSession

from backend.asr.model import get_model
from backend.asr.transcriber import Transcriber
from backend.config import settings
from backend.translation.moonshot import translate
from backend.storage.database import engine
from backend.storage.models import Session as SessionModel, Segment

INTERIM_INTERVAL = 0.4  # seconds between interim result pushes


async def handle_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Verify session exists
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

    print(f"[WS] Session {session_id} connected")

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.float32)
            result = transcriber.push_chunk(chunk)
            now = time.time()

            # Interim result: still speaking, push every INTERIM_INTERVAL seconds
            if result["should_interim"] and (now - last_interim_time) > INTERIM_INTERVAL:
                last_interim_time = now
                temp_audio = transcriber.audio_buffer.copy()
                segment_id = str(uuid4())
                interim_ts = transcriber.timestamp_ms  # capture NOW, before async delay

                async def _send_interim(audio, sid, ts):
                    txt = await asyncio.to_thread(
                        lambda: _transcribe_sync(audio)
                    )
                    if txt:
                        await websocket.send_text(json.dumps({
                            "id": sid, "status": "interim",
                            "ko": txt + "...", "zh": "识别中...",
                            "timestamp_ms": ts,
                        }, ensure_ascii=False))

                asyncio.create_task(_send_interim(temp_audio, segment_id, interim_ts))

            # Final result: VAD detected sentence end or buffer timeout
            elif result["should_process"]:
                final_audio = transcriber.audio_buffer.copy()
                final_id = str(uuid4())
                ts_ms = transcriber.timestamp_ms
                seq = segment_counter
                segment_counter += 1
                transcriber.commit()
                last_interim_time = time.time()

                async def _process_final(audio, seg_id, ts, s_id, seq_num):
                    ko = await asyncio.to_thread(lambda: _transcribe_sync(audio))
                    if not ko:
                        return

                    await websocket.send_text(json.dumps({
                        "id": seg_id, "status": "translating",
                        "ko": ko, "zh": "翻译中...", "timestamp_ms": ts,
                    }, ensure_ascii=False))

                    zh = await translate(ko)

                    await websocket.send_text(json.dumps({
                        "id": seg_id, "status": "done",
                        "ko": ko, "zh": zh, "timestamp_ms": ts,
                    }, ensure_ascii=False))

                    # Persist to database
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

                asyncio.create_task(_process_final(final_audio, final_id, ts_ms, session_id, seq))

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id} disconnected")
        _finalize_session(session_id)


def _transcribe_sync(audio: np.ndarray) -> str:
    """Run Whisper inference synchronously in a thread pool."""
    model = get_model()
    segments, _ = model.transcribe(
        audio, language="ko",
        beam_size=settings.asr_beam_size,
        vad_filter=False,
        condition_on_previous_text=True,
    )
    text = "".join(s.text for s in segments).strip()
    if any(w in text for w in settings.hallucination_blacklist) and len(text) < 25:
        return ""
    return text


def _finalize_session(session_id: str):
    """Update session end time when WebSocket closes."""
    with DBSession(engine) as db:
        sess = db.get(SessionModel, session_id)
        if sess and sess.ended_at is None:
            sess.ended_at = datetime.now(timezone.utc)
            if sess.started_at:
                delta = sess.ended_at - sess.started_at
                sess.duration_seconds = int(delta.total_seconds())
            db.commit()
