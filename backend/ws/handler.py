# backend/ws/handler.py
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session as DBSession, select

from backend.asr.transcriber import Transcriber, transcribe_audio
from backend.translation.moonshot import translate_stream
from backend.polish.translator import polish_translate, transcribe_long_form
from backend.storage.database import engine
from backend.storage.models import Session as SessionModel, Segment, PolishedChunk

# 录音 PCM 落盘目录。env 可覆盖（Windows 部署时指到 C:\leolee\data\raw 之类）
RAW_AUDIO_DIR = Path(os.getenv("RAW_AUDIO_DIR", "data/raw"))
RAW_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

INTERIM_INTERVAL = 2.5          # seconds between interim attempts (>1.2 → fewer GPU contention with finals)
MAX_CONTEXT_CHARS = 200         # rolling prompt is trimmed to this length
TRANSLATION_PUSH_MIN_INTERVAL = 0.1   # 流式翻译每 100ms 最多推一次 WS 更新（节流防止刷屏）
POLISH_INTERVAL_SEC = 60        # 精修循环间隔：每 60s 把窗口内的 segments 送 LLM 重译
POLISH_MIN_AUDIO_BYTES = 16000 * 4   # 1 秒 float32 音频 = 64 KB；不到 1s 不做精修
GRACEFUL_FINAL_MIN_SAMPLES = int(16000 * 0.5)  # graceful 收尾时 buffer 不到 0.5s 就不再 ASR

# One GPU slot at a time — module-level so it is shared across ALL sessions.
# On a single-GPU machine this is the correct behaviour: concurrent sessions
# share the same physical device and must not run inference simultaneously.
# Interims skip (non-blocking) if GPU is busy.
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

    # 原始 PCM 存盘：精修管道每 60s 从这里重新识别（比实时 5-8s 切片精度高很多）
    raw_pcm_path = RAW_AUDIO_DIR / f"{session_id}.pcm"
    raw_pcm_file = open(raw_pcm_path, "wb")

    # 精修管道共享状态：60s 节拍 loop 和 graceful/abrupt 收尾都要读写
    # 提到外层（不是 _polish_loop 局部）的目的：会话结束时收尾流程也能拿到 PCM 增量偏移
    polish_last_pcm_byte = 0
    polish_chunk_index = 0
    polish_last_processed_seq = -1

    print(f"[WS] Session {session_id} connected; raw PCM → {raw_pcm_path}")

    async def _safe_send(data: dict) -> bool:
        try:
            await websocket.send_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception:
            return False

    # ── 单次精修：读 PCM 增量 → long-form ASR → LLM polish → 写 DB → (可选) 推 WS
    # 被三处复用：60s 节拍 loop、graceful 收尾、abrupt 断开收尾
    async def _do_polish_iteration(send_ws: bool) -> bool:
        nonlocal polish_last_pcm_byte, polish_chunk_index, polish_last_processed_seq
        try:
            with open(raw_pcm_path, "rb") as f:
                f.seek(polish_last_pcm_byte)
                chunk_bytes = f.read()
        except FileNotFoundError:
            return False
        if len(chunk_bytes) < POLISH_MIN_AUDIO_BYTES:
            print(f"[Polish] window {polish_chunk_index} skipped (only {len(chunk_bytes)} bytes < 1s)")
            return False
        audio = np.frombuffer(chunk_bytes, dtype=np.float32).copy()
        bytes_consumed = len(chunk_bytes)

        async with _gpu_sem:
            ko_better = await asyncio.to_thread(lambda: transcribe_long_form(audio))
        if not ko_better:
            print(f"[Polish] window {polish_chunk_index} ASR returned empty")
            return False

        zh_polished = await polish_translate(ko_better)
        if not zh_polished:
            print(f"[Polish] window {polish_chunk_index} LLM returned empty")
            return False

        with DBSession(engine) as db:
            new_segs = db.exec(
                select(Segment)
                .where(Segment.session_id == session_id)
                .where(Segment.sequence > polish_last_processed_seq)
                .order_by(Segment.sequence)
            ).all()
            start_seq = new_segs[0].sequence if new_segs else 0
            end_seq = new_segs[-1].sequence if new_segs else 0
            pc = PolishedChunk(
                session_id=session_id,
                chunk_index=polish_chunk_index,
                start_segment_seq=start_seq,
                end_segment_seq=end_seq,
                ko_combined=ko_better,
                zh_polished=zh_polished,
            )
            db.add(pc)
            db.commit()
            db.refresh(pc)

        polish_last_pcm_byte += bytes_consumed
        if new_segs:
            polish_last_processed_seq = end_seq
        polish_chunk_index += 1

        if send_ws:
            await _safe_send({
                "status": "polish",
                "id": pc.id,
                "chunk_index": pc.chunk_index,
                "start_segment_seq": start_seq,
                "end_segment_seq": end_seq,
                "ko_combined": ko_better,
                "zh_polished": zh_polished,
                "created_at": pc.created_at.isoformat(),
            })
        print(f"[Polish] window {pc.chunk_index} done: {len(audio)/16000:.1f}s → {len(ko_better)} ko chars (ws={send_ws})")
        return True

    # ── 60s 节拍精修循环 ────────────────────────────────────────────
    # 单次失败（MLX OOM / Moonshot 429 等）只 log，不停掉整个 loop
    async def _polish_loop():
        try:
            while True:
                await asyncio.sleep(POLISH_INTERVAL_SEC)
                try:
                    await _do_polish_iteration(send_ws=True)
                except Exception as e:
                    print(f"[Polish] iteration error (loop continues): {type(e).__name__}: {e}")
        except asyncio.CancelledError:
            return

    # ── 单段 final segment 处理（识别 + 翻译 + 存 DB + 推 WS）
    # 主循环里 fire-and-forget 调用；graceful 收尾时 await 调用
    async def _process_final(audio, seg_id, ts, s_id, seq_num, context):
        nonlocal rolling_context

        rms = float(np.sqrt(np.mean(audio**2))) if len(audio) else 0.0
        print(
            f"[WS final ] seg={seg_id[:8]} dur={len(audio)/16000:.2f}s "
            f"rms={rms:.4f} ctx_tail={(context or '')[-24:]!r}"
        )

        # Semaphore only wraps Whisper — released before translation
        # so next sentence can start transcribing concurrently.
        # 不传 rolling_context 当 prompt：避免 Whisper "5. 자신의..." 类自循环。
        # rolling_context 仍然继续维护，留给后续翻译模块使用。
        async with _gpu_sem:
            ko = await asyncio.to_thread(
                lambda: transcribe_audio(audio, initial_prompt=None)
            )

        if not ko:
            print(f"[WS final ] seg={seg_id[:8]} EMPTY → removing card")
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

        # 流式翻译：边收 Moonshot token 边推 WS，让前端"立刻开始打字"
        # 节流：每 100ms 最多推一次，避免 token 级别（30/s）刷屏
        zh_acc = ""
        last_push = time.time()
        async for delta in translate_stream(ko):
            zh_acc += delta
            now = time.time()
            if now - last_push >= TRANSLATION_PUSH_MIN_INTERVAL:
                ok = await _safe_send({
                    "id": seg_id, "status": "translating",
                    "ko": ko, "zh": zh_acc, "timestamp_ms": ts,
                })
                if not ok:
                    return
                last_push = now

        # 终态：status=done，确保最后一次更新一定推到（前一次推可能因节流没赶上）
        await _safe_send({
            "id": seg_id, "status": "done",
            "ko": ko, "zh": zh_acc, "timestamp_ms": ts,
        })
        zh = zh_acc

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

    # ── graceful 收尾：用户主动 stop 时的完整流程 ─────────────────
    # 1) 把 transcriber 里未 commit 的尾音吐出来 → 跑 final ASR/翻译 → 推 WS
    # 2) 从 PCM 文件读最后一段未精修的字节 → 长稿 ASR + LLM polish → 推 WS
    # 这两步都是 await 同步执行，确保在 ws.close() 之前结果一定推出去
    async def _graceful_finalize():
        nonlocal current_seg_id, segment_counter
        # 1) flush transcriber 剩余音频（修问题 ③：尾巴丢失）
        if len(transcriber.audio_buffer) >= GRACEFUL_FINAL_MIN_SAMPLES:
            seg_id = current_seg_id or str(uuid4())
            current_seg_id = None
            ts_ms = transcriber.timestamp_ms
            seq = segment_counter
            segment_counter += 1
            # was_forced=False：把整个 buffer 吐出来，不留尾巴
            final_audio = transcriber.commit(was_forced=False)
            ctx = rolling_context
            try:
                await _process_final(final_audio, seg_id, ts_ms, session_id, seq, ctx)
            except Exception as e:
                print(f"[Graceful] tail final ASR/translate failed: {e}")
        else:
            print(f"[Graceful] transcriber buffer < 0.5s, skip tail final")

        # 2) 确保 PCM 落盘（_process_final 期间不接新音频，buffer 已写入）
        try:
            raw_pcm_file.flush()
        except Exception:
            pass

        # 3) 尾段 polish：从 PCM 高质量重做（修问题 ① ②）
        try:
            await _do_polish_iteration(send_ws=True)
        except Exception as e:
            print(f"[Graceful] tail polish failed: {e}")

    polish_task = asyncio.create_task(_polish_loop())
    graceful = False

    try:
        while True:
            # 用底层 receive() 同时接 bytes（PCM）和 text（控制消息如 stop）
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()

            if message.get("bytes") is not None:
                data = message["bytes"]
                # 同时存原始 PCM（精修管道每 60s 从这里重识别）
                raw_pcm_file.write(data)
                raw_pcm_file.flush()
                chunk = np.frombuffer(data, dtype=np.float32)
                result = transcriber.push_chunk(chunk)
                now = time.time()

                # ── Interim ──────────────────────────────────────────────
                if result["should_interim"] and (now - last_interim_time) > INTERIM_INTERVAL:
                    last_interim_time = now
                    is_new_segment = current_seg_id is None
                    if is_new_segment:
                        current_seg_id = str(uuid4())
                    sid = current_seg_id
                    ts = transcriber.timestamp_ms
                    temp_audio = transcriber.audio_buffer.copy()
                    ctx = rolling_context   # snapshot — do not mutate inside task

                    # 仅在段首推一次 "..." 占位卡，避免每个 1.2s 节拍把真实 ko 文本盖回 "..."
                    # 后续节拍只让 _update_interim 推真识别结果；GPU 忙时保留上次内容。
                    if is_new_segment:
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
                            # 不传 rolling_context 当 prompt：避免 Whisper "5. 자신의..." 类自循环
                            # 静态关键词 prompt（settings.asr_initial_prompt）足够给 ASR 提供领域提示
                            txt = await asyncio.to_thread(
                                lambda: transcribe_audio(audio, fast=True, initial_prompt=None)
                            )
                        if txt:
                            await _safe_send({
                                "id": seg_id, "status": "interim",
                                "ko": txt + "...", "zh": "识别中...",
                                "timestamp_ms": interim_ts,
                            })

                    asyncio.create_task(_update_interim(temp_audio, sid, ts, ctx))

                # ── Final ─────────────────────────────────────────────────
                elif result["should_process"]:
                    if current_seg_id is None:
                        current_seg_id = str(uuid4())
                    final_id = current_seg_id
                    current_seg_id = None
                    ts_ms = transcriber.timestamp_ms
                    seq = segment_counter
                    segment_counter += 1
                    # commit 现在自带智能切点逻辑：撞 8s 上限时在最后 1 秒里找最低 RMS 点切，
                    # 而不是从词中央切。返回的就是要送 Whisper 的音频快照。
                    final_audio = transcriber.commit(was_forced=result["is_forced"])
                    last_interim_time = time.time()
                    ctx = rolling_context   # snapshot for this segment's inference

                    asyncio.create_task(
                        _process_final(final_audio, final_id, ts_ms, session_id, seq, ctx)
                    )

            elif message.get("text"):
                # 控制消息：目前仅支持 {"action": "stop"} —— graceful 关闭信号
                try:
                    ctrl = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if ctrl.get("action") == "stop":
                    graceful = True
                    print(f"[WS] Session {session_id} graceful stop signal received")
                    break

    except WebSocketDisconnect:
        print(f"[WS] Session {session_id} disconnected (abrupt)")
    finally:
        # 总是先取消 60s 精修循环
        polish_task.cancel()
        try:
            await polish_task
        except asyncio.CancelledError:
            pass

        if graceful:
            # WS 还活着 → 同步等待收尾流程，确保 final + polish 帧都推到前端
            try:
                await _graceful_finalize()
            except Exception as e:
                print(f"[Graceful] finalize error: {e}")
            try:
                raw_pcm_file.flush()
                raw_pcm_file.close()
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
        else:
            # 异常断开 → 写 DB 不推 WS（用户能在 history 页查到）
            try:
                raw_pcm_file.flush()
                raw_pcm_file.close()
            except Exception:
                pass
            try:
                await _do_polish_iteration(send_ws=False)
            except Exception as e:
                print(f"[Abrupt] tail polish error: {e}")

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
