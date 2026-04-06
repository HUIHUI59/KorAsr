# korAsr Complete Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有单文件 ASR 原型重写为模块化 FastAPI 后端 + Vue 3 前端，集成 Silero VAD 提升断句精度，并新增会话持久化、AI 总结、历史记录等功能。

**Architecture:** FastAPI 后端分 5 个模块（asr/translation/storage/summary/ws）+ REST API 层，通过 SQLite 持久化会话数据，Moonshot API 负责翻译和 AI 总结。Vue 3 + Vite 前端，响应式适配桌面端（左右分栏）和移动端（Tab 切换）。

**Tech Stack:** Python 3.11+, FastAPI, Faster-Whisper, Silero VAD, SQLModel, OpenAI SDK, Vue 3, Vite, Pinia, Vue Router

---

## 文件结构总览

```
korAsr/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── asr/
│   │   ├── __init__.py
│   │   ├── model.py
│   │   ├── vad.py
│   │   └── transcriber.py
│   ├── translation/
│   │   ├── __init__.py
│   │   └── moonshot.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── models.py
│   ├── summary/
│   │   ├── __init__.py
│   │   └── generator.py
│   ├── ws/
│   │   ├── __init__.py
│   │   └── handler.py
│   └── api/
│       ├── __init__.py
│       ├── sessions.py
│       └── export.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TranscriptFeed.vue
│   │   │   ├── NotesPad.vue
│   │   │   ├── StatusBar.vue
│   │   │   └── SessionHistory.vue
│   │   ├── views/
│   │   │   ├── ClassroomView.vue
│   │   │   └── HistoryView.vue
│   │   ├── stores/
│   │   │   └── session.js
│   │   ├── router/
│   │   │   └── index.js
│   │   └── App.vue
│   ├── package.json
│   └── vite.config.js
├── data/                    # SQLite DB 存储目录（git ignore）
├── .env                     # 实际配置（git ignore）
├── .env.example
└── requirements.txt
```

---

## Phase 1：后端核心

### Task 1：项目脚手架 + 依赖配置

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `backend/__init__.py` 及所有子包 `__init__.py`

- [ ] **Step 1: 写 requirements.txt**

```text
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
faster-whisper>=1.0.0
torch>=2.2.0
torchaudio>=2.2.0
openai>=1.30.0
sqlmodel>=0.0.18
pydantic-settings>=2.2.0
numpy>=1.26.0
python-multipart>=0.0.9
```

- [ ] **Step 2: 写 .env.example**

```ini
MOONSHOT_API_KEY=sk-your-key-here

ASR_MODEL=large-v3
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_BEAM_SIZE=5
ASR_MAX_BUFFER_S=8.0
ASR_MIN_BUFFER_S=0.5

VAD_THRESHOLD=0.5
VAD_MIN_SILENCE_MS=600
VAD_MIN_SPEECH_MS=250

HALLUCINATION_BLACKLIST=자막,감사합니다,시청해주셔서,구독,좋아요,MBC,SBS,KBS
```

- [ ] **Step 3: 写 .gitignore**

```gitignore
.env
data/
__pycache__/
*.pyc
*.pyo
.venv/
node_modules/
frontend/dist/
.superpowers/
```

- [ ] **Step 4: 创建所有 __init__.py**

```bash
mkdir -p backend/asr backend/translation backend/storage backend/summary backend/ws backend/api data
touch backend/__init__.py backend/asr/__init__.py backend/translation/__init__.py
touch backend/storage/__init__.py backend/summary/__init__.py backend/ws/__init__.py backend/api/__init__.py
```

- [ ] **Step 5: 复制 .env.example 为 .env，填入真实 API Key**

```bash
cp .env.example .env
# 编辑 .env，填入 MOONSHOT_API_KEY
```

- [ ] **Step 6: 安装依赖**

```bash
pip install -r requirements.txt
```

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt .env.example .gitignore backend/
git commit -m "chore: project scaffold with dependencies"
```

---

### Task 2：配置模块

**Files:**
- Create: `backend/config.py`

- [ ] **Step 1: 写 config.py**

```python
# backend/config.py
from pydantic_settings import BaseSettings
from typing import List

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

    hallucination_blacklist: List[str] = [
        "자막", "감사합니다", "시청해주셔서", "구독", "좋아요", "MBC", "SBS", "KBS"
    ]

    model_config = {"env_file": ".env"}

settings = Settings()
```

- [ ] **Step 2: 验证配置加载**

```bash
cd backend
python -c "from config import settings; print('API Key loaded:', bool(settings.moonshot_api_key))"
```

预期输出：`API Key loaded: True`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat: add config module with pydantic-settings"
```

---

### Task 3：数据库模型 + 初始化

**Files:**
- Create: `backend/storage/models.py`
- Create: `backend/storage/database.py`

- [ ] **Step 1: 写 models.py**

```python
# backend/storage/models.py
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    segment_count: int = 0
    summary: Optional[str] = None
    notes: Optional[str] = None
    segments: List["Segment"] = Relationship(back_populates="session")

class Segment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    sequence: int
    timestamp_ms: int
    ko_text: str
    zh_text: Optional[str] = None
    is_starred: bool = False
    session: Optional[Session] = Relationship(back_populates="segments")
```

- [ ] **Step 2: 写 database.py**

```python
# backend/storage/database.py
from sqlmodel import SQLModel, create_engine, Session as DBSession
from pathlib import Path

DB_PATH = Path("data/korasr.db")
DB_PATH.parent.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_db():
    with DBSession(engine) as session:
        yield session
```

- [ ] **Step 3: 验证 DB 创建**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from backend.storage.database import init_db
init_db()
print('DB created at data/korasr.db')
"
```

预期：`DB created at data/korasr.db`，且 `data/korasr.db` 文件存在

- [ ] **Step 4: Commit**

```bash
git add backend/storage/
git commit -m "feat: add SQLite storage with Session and Segment models"
```

---

### Task 4：Silero VAD 模块

**Files:**
- Create: `backend/asr/vad.py`

- [ ] **Step 1: 写 vad.py**

```python
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
```

- [ ] **Step 2: 验证 VAD 加载**

```bash
python -c "
import sys; sys.path.insert(0, '.')
import numpy as np
from backend.asr.vad import SileroVAD
vad = SileroVAD()
silence = np.zeros(4096, dtype=np.float32)
result = vad.process_chunk(silence)
print('VAD OK, prob:', result['speech_prob'])
"
```

预期：`VAD OK, prob: <接近0的数值>`（首次运行会下载模型，约几十MB）

- [ ] **Step 3: Commit**

```bash
git add backend/asr/vad.py
git commit -m "feat: add Silero VAD for accurate sentence boundary detection"
```

---

### Task 5：ASR 模型 + 转录调度器

**Files:**
- Create: `backend/asr/model.py`
- Create: `backend/asr/transcriber.py`

- [ ] **Step 1: 写 model.py（单例加载）**

```python
# backend/asr/model.py
import warnings
warnings.filterwarnings("ignore")

from faster_whisper import WhisperModel
from backend.config import settings

_model: WhisperModel | None = None

def get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[ASR] 加载 Whisper {settings.asr_model} on {settings.asr_device}...")
        _model = WhisperModel(
            settings.asr_model,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
        )
        print("[ASR] 模型加载完成")
    return _model
```

- [ ] **Step 2: 写 transcriber.py**

```python
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
        推入一个音频块。返回 {'should_process': bool, 'should_interim': bool}
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
        self._buffer_start_s = (len(self.audio_buffer) / SAMPLE_RATE)
        self.vad.reset()
```


- [ ] **Step 3: 验证 transcriber 初始化（不运行推理，只检查加载）**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from backend.asr.transcriber import Transcriber
t = Transcriber()
print('Transcriber ready, buffer:', t.buffer_seconds, 's')
"
```

预期：Whisper 模型加载日志 + `Transcriber ready, buffer: 0.0 s`

- [ ] **Step 4: Commit**

```bash
git add backend/asr/
git commit -m "feat: add ASR model singleton and Transcriber with Silero VAD scheduling"
```

---

### Task 6：翻译模块

**Files:**
- Create: `backend/translation/moonshot.py`

- [ ] **Step 1: 写 moonshot.py**

```python
# backend/translation/moonshot.py
import asyncio
from openai import AsyncOpenAI
from backend.config import settings

_client: AsyncOpenAI | None = None

def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.moonshot_api_key,
            base_url="https://api.moonshot.cn/v1",
        )
    return _client

SYSTEM_PROMPT = (
    "你是一位专业的韩中同传翻译官。"
    "请将输入的韩语口语翻译成自然、流畅的中文，修正断句中的重复，"
    "不需要任何解释，直接输出最终的中文译文。"
)

async def translate(text: str) -> str:
    """将韩语文本异步翻译为中文。失败时返回空字符串。"""
    if not text or len(text) < 2:
        return ""
    try:
        client = get_client()
        completion = await client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Translation] 错误: {e}")
        return ""
```

- [ ] **Step 2: 验证翻译（需要真实 API Key）**

```bash
python -c "
import asyncio, sys
sys.path.insert(0, '.')
from backend.translation.moonshot import translate
result = asyncio.run(translate('안녕하세요, 오늘 수업을 시작하겠습니다.'))
print('翻译结果:', result)
"
```

预期：`翻译结果: 大家好，我们今天开始上课。`（或类似中文）

- [ ] **Step 3: Commit**

```bash
git add backend/translation/
git commit -m "feat: add async Moonshot translation module"
```

---

### Task 7：AI 总结模块

**Files:**
- Create: `backend/summary/generator.py`

- [ ] **Step 1: 写 generator.py**

```python
# backend/summary/generator.py
from backend.translation.moonshot import get_client
from backend.storage.models import Segment

SUMMARY_SYSTEM_PROMPT = """你是一位专业的学术助手。
请根据以下课堂实录（韩语原文+中文翻译），生成一份结构化的中文课堂笔记。

输出格式（严格按照以下 Markdown 结构）：

## 主要内容
1. （要点一）
2. （要点二）
...

## 关键概念
- **术语（韩语）**：中文解释

## 重要句子
> 原文引用 — 中文翻译

## 待跟进
- [ ] 需要进一步查阅的内容"""

async def generate_summary(segments: list[Segment]) -> str:
    """根据会话的所有片段生成 AI 总结。"""
    if not segments:
        return ""

    transcript_lines = [
        f"[{s.timestamp_ms // 1000 // 60:02d}:{s.timestamp_ms // 1000 % 60:02d}] {s.ko_text} | {s.zh_text or '（翻译缺失）'}"
        for s in sorted(segments, key=lambda x: x.sequence)
    ]
    transcript = "\n".join(transcript_lines)

    client = get_client()
    try:
        completion = await client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是课堂实录：\n\n{transcript}"},
            ],
            temperature=0.4,
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Summary] 错误: {e}")
        return ""
```

- [ ] **Step 2: Commit**

```bash
git add backend/summary/
git commit -m "feat: add AI summary generator using Moonshot"
```

---

### Task 8：WebSocket 处理器

**Files:**
- Create: `backend/ws/handler.py`

- [ ] **Step 1: 写 handler.py**

```python
# backend/ws/handler.py
import asyncio
import json
import time
from uuid import uuid4

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session as DBSession, select

from backend.asr.transcriber import Transcriber
from backend.translation.moonshot import translate
from backend.storage.database import engine
from backend.storage.models import Session as SessionModel, Segment

INTERIM_INTERVAL = 0.4  # 秒，中间结果推送间隔


async def handle_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # 验证 session 存在
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

    print(f"[WS] 会话 {session_id} 连接建立")

    try:
        while True:
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.float32)
            result = transcriber.push_chunk(chunk)
            now = time.time()

            # 中间结果：说话中，每 INTERIM_INTERVAL 推一次
            if result["should_interim"] and (now - last_interim_time) > INTERIM_INTERVAL:
                last_interim_time = now
                temp_audio = transcriber.audio_buffer.copy()
                segment_id = str(uuid4())

                async def _send_interim(audio, sid):
                    txt = await asyncio.to_thread(
                        lambda: _transcribe_sync(audio)
                    )
                    if txt:
                        await websocket.send_text(json.dumps({
                            "id": sid, "status": "interim",
                            "ko": txt + "...", "zh": "识别中...",
                            "timestamp_ms": transcriber.timestamp_ms,
                        }, ensure_ascii=False))

                asyncio.create_task(_send_interim(temp_audio, segment_id))

            # 最终结果：VAD 检测到断句或缓冲超时
            elif result["should_process"]:
                final_audio = transcriber.audio_buffer.copy()
                final_id = str(uuid4())
                ts_ms = transcriber.timestamp_ms
                seq = segment_counter
                segment_counter += 1
                transcriber.commit()
                last_interim_time = time.time()

                async def _process_final(audio, seg_id, ts, s_id, seq_num):
                    ko = await asyncio.to_thread(lambda: _transcribe_sync(transcriber, audio))
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

                    # 持久化到数据库
                    with DBSession(engine) as db:
                        seg = Segment(
                            id=seg_id, session_id=s_id,
                            sequence=seq_num, timestamp_ms=ts,
                            ko_text=ko, zh_text=zh,
                        )
                        db.add(seg)
                        # 更新会话片段计数
                        sess = db.get(SessionModel, s_id)
                        if sess:
                            sess.segment_count += 1
                        db.commit()

                asyncio.create_task(_process_final(final_audio, final_id, ts_ms, session_id, seq))

    except WebSocketDisconnect:
        print(f"[WS] 会话 {session_id} 断开")
        _finalize_session(session_id)


def _transcribe_sync(audio: np.ndarray) -> str:
    """在线程池中同步执行转录"""
    from faster_whisper import WhisperModel
    from backend.asr.model import get_model
    from backend.config import settings

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
    """WebSocket 关闭时更新会话结束时间"""
    from datetime import datetime
    with DBSession(engine) as db:
        sess = db.get(SessionModel, session_id)
        if sess and sess.ended_at is None:
            sess.ended_at = datetime.utcnow()
            if sess.started_at:
                delta = sess.ended_at - sess.started_at
                sess.duration_seconds = int(delta.total_seconds())
            db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/ws/
git commit -m "feat: add WebSocket handler with Silero VAD + async translation + DB persistence"
```

---

## Phase 2：REST API + 主应用

### Task 9：REST API（会话管理 + 导出 + AI 总结）

**Files:**
- Create: `backend/api/sessions.py`
- Create: `backend/api/export.py`

- [ ] **Step 1: 写 sessions.py**

```python
# backend/api/sessions.py
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession, select
from pydantic import BaseModel

from backend.storage.database import get_db
from backend.storage.models import Session as SessionModel, Segment
from backend.summary.generator import generate_summary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    name: str


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None


@router.post("", status_code=201)
def create_session(body: SessionCreate, db: DBSession = Depends(get_db)):
    sess = SessionModel(name=body.name)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@router.get("")
def list_sessions(db: DBSession = Depends(get_db)):
    sessions = db.exec(
        select(SessionModel).order_by(SessionModel.started_at.desc())
    ).all()
    return sessions


@router.get("/{session_id}")
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment)
        .where(Segment.session_id == session_id)
        .order_by(Segment.sequence)
    ).all()
    return {"session": sess, "segments": segments}


@router.patch("/{session_id}")
def update_session(session_id: str, body: SessionUpdate, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if body.name is not None:
        sess.name = body.name
    if body.notes is not None:
        sess.notes = body.notes
    db.commit()
    db.refresh(sess)
    return sess


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    db.exec(select(Segment).where(Segment.session_id == session_id))
    for seg in db.exec(select(Segment).where(Segment.session_id == session_id)).all():
        db.delete(seg)
    db.delete(sess)
    db.commit()


@router.post("/{session_id}/summary")
async def trigger_summary(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment).where(Segment.session_id == session_id).order_by(Segment.sequence)
    ).all()
    summary = await generate_summary(list(segments))
    sess.summary = summary
    db.commit()
    return {"summary": summary}


class SegmentUpdate(BaseModel):
    is_starred: Optional[bool] = None
    zh_text: Optional[str] = None
```

- [ ] **Step 2: 写 export.py**

```python
# backend/api/export.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session as DBSession, select

from backend.storage.database import get_db
from backend.storage.models import Session as SessionModel, Segment

router = APIRouter(prefix="/api/sessions", tags=["export"])


@router.get("/{session_id}/export")
def export_session(
    session_id: str,
    format: str = "txt",
    db: DBSession = Depends(get_db),
):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment)
        .where(Segment.session_id == session_id)
        .order_by(Segment.sequence)
    ).all()

    if format == "txt":
        lines = [f"# {sess.name}", f"# {sess.started_at.strftime('%Y-%m-%d %H:%M')}", ""]
        for seg in segments:
            mm = seg.timestamp_ms // 1000 // 60
            ss = seg.timestamp_ms // 1000 % 60
            lines.append(f"[{mm:02d}:{ss:02d}] {seg.ko_text} | {seg.zh_text or ''}")
        if sess.notes:
            lines += ["", "=== 我的笔记 ===", sess.notes]
        content = "\n".join(lines)
        filename = f"{sess.name}.txt"
        return PlainTextResponse(
            content=content,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    elif format == "md":
        lines = [
            f"# {sess.name}",
            f"**日期**: {sess.started_at.strftime('%Y-%m-%d')}  ",
            f"**时长**: {sess.duration_seconds // 60 if sess.duration_seconds else 0} 分钟  ",
            f"**片段数**: {sess.segment_count}",
            "",
            "## 原始记录",
            "",
            "| 时间 | 韩语 | 中文翻译 |",
            "|------|------|----------|",
        ]
        for seg in segments:
            mm = seg.timestamp_ms // 1000 // 60
            ss = seg.timestamp_ms // 1000 % 60
            star = "⭐ " if seg.is_starred else ""
            lines.append(f"| {mm:02d}:{ss:02d} | {star}{seg.ko_text} | {seg.zh_text or ''} |")

        if sess.summary:
            lines += ["", "## AI 总结", "", sess.summary]
        if sess.notes:
            lines += ["", "## 我的笔记", "", sess.notes]

        content = "\n".join(lines)
        filename = f"{sess.name}.md"
        return PlainTextResponse(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(400, "format must be 'txt' or 'md'")
```

- [ ] **Step 3: Commit**

```bash
git add backend/api/
git commit -m "feat: add REST API for session CRUD, export (txt/md), and AI summary trigger"
```

---

### Task 10：FastAPI 主应用 + 后端验证

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: 写 main.py**

```python
# backend/main.py
import warnings
warnings.filterwarnings("ignore")

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.storage.database import init_db
from backend.api.sessions import router as sessions_router
from backend.api.export import router as export_router
from backend.ws.handler import handle_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] 初始化数据库...")
    init_db()
    # 预加载 ASR 模型（避免首次请求延迟）
    from backend.asr.model import get_model
    get_model()
    print("[Startup] 就绪")
    yield
    print("[Shutdown] 服务关闭")


app = FastAPI(title="korAsr", lifespan=lifespan)

# REST API 路由
app.include_router(sessions_router)
app.include_router(export_router)


# WebSocket 端点
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_ws(websocket, session_id)


# 服务前端静态文件（生产环境）
FRONTEND_DIST = Path("frontend/dist")
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return {"status": "ok", "message": "Backend running. Start frontend with: cd frontend && npm run dev"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
```

- [ ] **Step 2: 启动后端，验证 API 可用**

```bash
python -m backend.main
```

打开浏览器访问 `http://localhost:8000/docs`，验证以下端点存在：
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{id}`
- `GET /api/sessions/{id}/export`
- `POST /api/sessions/{id}/summary`

- [ ] **Step 3: 手动测试 API（用 curl 或 Swagger UI）**

```bash
# 创建会话
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "테스트 세션"}'
# 预期：返回 session JSON，含 id

# 查询会话列表
curl http://localhost:8000/api/sessions
# 预期：包含刚创建的会话
```

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: add FastAPI main app with lifespan, WebSocket, and SPA serving"
```

---

## Phase 3：前端（Vue 3 + Vite）

### Task 11：Vue 3 项目脚手架 + 路由 + 状态管理

**Files:**
- Create: `frontend/` (Vite 生成)
- Create: `frontend/vite.config.js`
- Create: `frontend/src/router/index.js`
- Create: `frontend/src/stores/session.js`
- Create: `frontend/src/App.vue`

- [ ] **Step 1: 初始化 Vue 3 项目**

```bash
cd C:/AI/korAsr
npm create vite@latest frontend -- --template vue
cd frontend
npm install
npm install vue-router@4 pinia axios
```

- [ ] **Step 2: 配置 vite.config.js（代理到后端）**

```javascript
// frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
```

- [ ] **Step 3: 写 router/index.js**

```javascript
// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import ClassroomView from '../views/ClassroomView.vue'
import HistoryView from '../views/HistoryView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ClassroomView },
    { path: '/history', component: HistoryView },
  ],
})
```

- [ ] **Step 4: 写 stores/session.js（Pinia）**

```javascript
// frontend/src/stores/session.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useSessionStore = defineStore('session', () => {
  // 状态
  const currentSessionId = ref(null)
  const sessionName = ref('')
  const segments = ref([])   // { id, status, ko, zh, timestamp_ms, is_starred }
  const isRecording = ref(false)
  const isConnected = ref(false)
  const elapsedMs = ref(0)
  const notes = ref('')

  let ws = null
  let timerInterval = null
  let notesSaveTimeout = null

  // 计算属性
  const elapsedFormatted = computed(() => {
    const total = Math.floor(elapsedMs.value / 1000)
    const m = Math.floor(total / 60).toString().padStart(2, '0')
    const s = (total % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  })

  // 开始录音
  async function startSession(name) {
    const res = await axios.post('/api/sessions', { name })
    currentSessionId.value = res.data.id
    sessionName.value = name
    segments.value = []
    notes.value = ''
    elapsedMs.value = 0

    // 连接 WebSocket
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/${res.data.id}`)

    ws.onopen = () => {
      isConnected.value = true
      isRecording.value = true
      timerInterval = setInterval(() => { elapsedMs.value += 100 }, 100)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      const idx = segments.value.findIndex(s => s.id === data.id)
      if (idx >= 0) {
        segments.value[idx] = { ...segments.value[idx], ...data }
      } else {
        segments.value.push({ ...data, is_starred: false })
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      isRecording.value = false
      clearInterval(timerInterval)
    }

    return res.data.id
  }

  // 停止录音
  function stopSession() {
    if (ws) ws.close()
    isRecording.value = false
  }

  // 标记重点
  async function toggleStar(segmentId) {
    const seg = segments.value.find(s => s.id === segmentId)
    if (!seg) return
    seg.is_starred = !seg.is_starred
    await axios.patch(`/api/segments/${segmentId}`, { is_starred: seg.is_starred })
  }

  // 保存笔记（防抖）
  function saveNotes(text) {
    notes.value = text
    clearTimeout(notesSaveTimeout)
    notesSaveTimeout = setTimeout(async () => {
      if (currentSessionId.value) {
        await axios.patch(`/api/sessions/${currentSessionId.value}`, { notes: text })
      }
    }, 1000)
  }

  return {
    currentSessionId, sessionName, segments, isRecording, isConnected,
    elapsedMs, elapsedFormatted, notes,
    startSession, stopSession, toggleStar, saveNotes,
  }
})
```

- [ ] **Step 5: 写 App.vue**

```vue
<!-- frontend/src/App.vue -->
<template>
  <router-view />
</template>

<script setup>
</script>
```

- [ ] **Step 6: 更新 main.js**

```javascript
// frontend/src/main.js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index.js'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
```

- [ ] **Step 7: 启动前端开发服务器，确认无报错**

```bash
cd frontend && npm run dev
```

打开 `http://localhost:5173`，应看到空白页面（无报错）

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vue 3 + Vite + Pinia + Vue Router frontend"
```

---

### Task 12：核心组件 + ClassroomView

**Files:**
- Create: `frontend/src/components/StatusBar.vue`
- Create: `frontend/src/components/TranscriptFeed.vue`
- Create: `frontend/src/components/NotesPad.vue`
- Create: `frontend/src/views/ClassroomView.vue`

- [ ] **Step 1: 写 StatusBar.vue**

```vue
<!-- frontend/src/components/StatusBar.vue -->
<template>
  <div class="status-bar">
    <div class="left">
      <span class="dot" :class="{ active: isRecording, error: !isConnected && !isRecording }"></span>
      <input
        v-if="isRecording"
        class="session-name-input"
        :value="sessionName"
        @blur="$emit('rename', $event.target.value)"
      />
      <span v-else class="session-name">{{ sessionName || '未命名会话' }}</span>
      <span v-if="isRecording" class="timer">{{ elapsedFormatted }}</span>
    </div>
    <div class="right">
      <button v-if="!isRecording" class="btn btn-start" @click="$emit('start')">开始同传</button>
      <template v-else>
        <button class="btn btn-summary" @click="$emit('summary')">✦ AI总结</button>
        <button class="btn btn-stop" @click="$emit('stop')">■ 停止</button>
      </template>
      <router-link to="/history" class="btn btn-history">历史</router-link>
    </div>
  </div>
</template>

<script setup>
defineProps(['isRecording', 'isConnected', 'sessionName', 'elapsedFormatted'])
defineEmits(['start', 'stop', 'summary', 'rename'])
</script>

<style scoped>
.status-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  position: sticky; top: 0; z-index: 10;
}
.left { display: flex; align-items: center; gap: 10px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #8e8e93; }
.dot.active { background: #34c759; box-shadow: 0 0 6px #34c759; animation: pulse 1.5s infinite; }
.dot.error { background: #ff3b30; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.session-name { font-weight: 600; font-size: 15px; }
.session-name-input {
  font-weight: 600; font-size: 15px; border: none; outline: none;
  border-bottom: 1px dashed #ccc; background: transparent; min-width: 200px;
}
.timer { font-size: 13px; color: #888; font-family: monospace; }
.right { display: flex; gap: 8px; }
.btn { padding: 7px 14px; border-radius: 10px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; text-decoration: none; }
.btn-start { background: #5856d6; color: #fff; }
.btn-stop { background: #ff3b30; color: #fff; }
.btn-summary { background: #f0f0f5; color: #5856d6; }
.btn-history { background: #f0f0f5; color: #333; }
</style>
```

- [ ] **Step 2: 写 TranscriptFeed.vue**

```vue
<!-- frontend/src/components/TranscriptFeed.vue -->
<template>
  <div class="feed" ref="feedEl">
    <div v-if="segments.length === 0" class="empty">等待语音输入...</div>
    <div
      v-for="seg in segments"
      :key="seg.id"
      class="card"
      :class="seg.status"
    >
      <button class="star" :class="{ active: seg.is_starred }" @click="$emit('star', seg.id)">
        {{ seg.is_starred ? '★' : '☆' }}
      </button>
      <div class="ko">{{ seg.ko }}</div>
      <div class="zh" :class="{ pending: seg.status !== 'done' }">{{ seg.zh }}</div>
      <div class="ts">{{ formatTs(seg.timestamp_ms) }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
const props = defineProps(['segments'])
defineEmits(['star'])
const feedEl = ref(null)

watch(() => props.segments.length, async () => {
  await nextTick()
  if (feedEl.value) feedEl.value.scrollTop = feedEl.value.scrollHeight
})

function formatTs(ms) {
  if (!ms && ms !== 0) return ''
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60).toString().padStart(2, '0')
  const s = (total % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}
</script>

<style scoped>
.feed { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.empty { color: #aaa; text-align: center; margin-top: 40px; font-style: italic; }
.card {
  padding: 12px 14px; border-radius: 12px; border-left: 4px solid #5856d6;
  background: #f8f8fc; animation: fadeUp .3s ease; position: relative;
}
.card.interim { border-left-color: #ff9500; background: #fffcf0; }
.card.translating { border-left-color: #5856d6; }
@keyframes fadeUp { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.star { position: absolute; top: 10px; right: 12px; background: none; border: none; cursor: pointer; font-size: 16px; opacity: .4; }
.star.active { opacity: 1; }
.ko { font-size: 15px; font-weight: 600; line-height: 1.5; padding-right: 24px; }
.zh { font-size: 13px; color: #636366; margin-top: 4px; line-height: 1.5; }
.zh.pending { color: #aaa; font-style: italic; animation: blink 1s infinite alternate; }
@keyframes blink { 0%{opacity:1} 100%{opacity:.4} }
.ts { font-size: 11px; color: #c7c7cc; margin-top: 6px; }
</style>
```

- [ ] **Step 3: 写 NotesPad.vue**

```vue
<!-- frontend/src/components/NotesPad.vue -->
<template>
  <div class="notes-pad">
    <div class="header">
      <span>📝 我的笔记</span>
      <span class="saved-hint" v-if="savedHint">已保存</span>
    </div>
    <textarea
      class="editor"
      placeholder="在这里记录重点、问题、想法..."
      :value="modelValue"
      @input="onInput"
    ></textarea>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const props = defineProps(['modelValue'])
const emit = defineEmits(['update:modelValue'])
const savedHint = ref(false)
let hintTimer = null

function onInput(e) {
  emit('update:modelValue', e.target.value)
  clearTimeout(hintTimer)
  savedHint.value = false
  hintTimer = setTimeout(() => { savedHint.value = true }, 1200)
}
</script>

<style scoped>
.notes-pad { display: flex; flex-direction: column; height: 100%; border-left: 1px solid #f0f0f0; }
.header {
  padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #f0f0f0;
  font-size: 13px; font-weight: 700; display: flex; justify-content: space-between;
}
.saved-hint { font-size: 12px; color: #34c759; font-weight: 400; }
.editor {
  flex: 1; padding: 14px 16px; border: none; outline: none; resize: none;
  font-size: 13px; line-height: 1.7; font-family: inherit; background: #fff;
}
</style>
```

- [ ] **Step 4: 写 ClassroomView.vue**

```vue
<!-- frontend/src/views/ClassroomView.vue -->
<template>
  <div class="classroom">
    <StatusBar
      :is-recording="store.isRecording"
      :is-connected="store.isConnected"
      :session-name="store.sessionName"
      :elapsed-formatted="store.elapsedFormatted"
      @start="onStart"
      @stop="onStop"
      @summary="onSummary"
      @rename="onRename"
    />

    <!-- 桌面端：左右分栏 -->
    <div class="desktop-layout" v-if="!isMobile">
      <TranscriptFeed :segments="store.segments" @star="store.toggleStar" class="feed-panel" />
      <NotesPad v-model="notesModel" class="notes-panel" />
    </div>

    <!-- 移动端：Tab 切换 -->
    <div class="mobile-layout" v-else>
      <div class="tab-bar">
        <button :class="{ active: activeTab === 'feed' }" @click="activeTab = 'feed'">翻译</button>
        <button :class="{ active: activeTab === 'notes' }" @click="activeTab = 'notes'">笔记</button>
      </div>
      <TranscriptFeed v-if="activeTab === 'feed'" :segments="store.segments" @star="store.toggleStar" />
      <NotesPad v-else v-model="notesModel" style="flex:1" />
    </div>

    <!-- 开始对话框 -->
    <div class="start-modal" v-if="showStartModal" @click.self="showStartModal = false">
      <div class="modal-card">
        <h3>新建会话</h3>
        <input v-model="newSessionName" placeholder="如：경제학개론 4월 6일" @keyup.enter="confirmStart" autofocus />
        <div class="modal-btns">
          <button class="btn-cancel" @click="showStartModal = false">取消</button>
          <button class="btn-confirm" @click="confirmStart">开始</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useSessionStore } from '../stores/session.js'
import StatusBar from '../components/StatusBar.vue'
import TranscriptFeed from '../components/TranscriptFeed.vue'
import NotesPad from '../components/NotesPad.vue'
import axios from 'axios'

const store = useSessionStore()
const isMobile = computed(() => window.innerWidth < 768)
const activeTab = ref('feed')
const showStartModal = ref(false)
const newSessionName = ref('')

const notesModel = computed({
  get: () => store.notes,
  set: (v) => store.saveNotes(v),
})

function onStart() {
  newSessionName.value = new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' }) + ' 수업'
  showStartModal.value = true
}

async function confirmStart() {
  if (!newSessionName.value.trim()) return
  showStartModal.value = false
  const sessionId = await store.startSession(newSessionName.value.trim())
  await startMicrophone(sessionId)
}

async function startMicrophone(sessionId) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const ctx = new AudioContext({ sampleRate: 16000 })
    const source = ctx.createMediaStreamSource(stream)
    const processor = ctx.createScriptProcessor(4096, 1, 1)
    source.connect(processor)
    processor.connect(ctx.destination)

    processor.onaudioprocess = (e) => {
      // WebSocket 连接由 store.startSession() 建立，直接发送
      // store 内部 ws 是私有的，需要通过 store 暴露 sendAudio 方法
      // 此处简化：直接访问 store 内部 ws（Task 13 中将 ws 暴露为 store 方法）
      store._sendAudio(e.inputBuffer.getChannelData(0).buffer)
    }

    // 停止时关闭音频
    const unwatchRecording = watch(() => store.isRecording, (v) => {
      if (!v) {
        processor.disconnect()
        stream.getTracks().forEach(t => t.stop())
        ctx.close()
        unwatchRecording()
      }
    })
  } catch (e) {
    alert('麦克风访问失败：' + e.message)
  }
}

function onStop() { store.stopSession() }
function onRename(name) {
  if (store.currentSessionId) {
    axios.patch(`/api/sessions/${store.currentSessionId}`, { name })
  }
}
async function onSummary() {
  if (!store.currentSessionId) return
  const res = await axios.post(`/api/sessions/${store.currentSessionId}/summary`)
  alert('AI总结已生成！\n\n' + res.data.summary.substring(0, 200) + '...')
}
</script>

<style scoped>
.classroom { display: flex; flex-direction: column; height: 100vh; }
.desktop-layout { display: flex; flex: 1; overflow: hidden; }
.feed-panel { flex: 0 0 65%; display: flex; flex-direction: column; }
.notes-panel { flex: 0 0 35%; display: flex; flex-direction: column; }
.mobile-layout { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
.tab-bar { display: flex; border-bottom: 1px solid #f0f0f0; }
.tab-bar button { flex: 1; padding: 10px; border: none; background: #fafafa; font-size: 13px; font-weight: 600; cursor: pointer; }
.tab-bar button.active { background: #fff; color: #5856d6; border-bottom: 2px solid #5856d6; }

/* 开始模态框 */
.start-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal-card { background: #fff; border-radius: 16px; padding: 24px; width: 320px; }
.modal-card h3 { margin: 0 0 16px; font-size: 17px; }
.modal-card input {
  width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 10px;
  font-size: 14px; outline: none; box-sizing: border-box;
}
.modal-btns { display: flex; gap: 10px; margin-top: 16px; justify-content: flex-end; }
.btn-cancel { padding: 8px 16px; border: none; background: #f0f0f5; border-radius: 10px; cursor: pointer; }
.btn-confirm { padding: 8px 16px; border: none; background: #5856d6; color: #fff; border-radius: 10px; cursor: pointer; font-weight: 600; }
</style>
```

- [ ] **Step 5: 在 stores/session.js 中暴露 _sendAudio 方法**

在 `stores/session.js` 的 `return` 语句中，暴露 `_sendAudio`，并在 store 内添加该方法：

```javascript
// 在 startSession 函数内，ws.onopen 后添加：
// （ws 已是 let ws = null，在 startSession 内赋值）

// 暴露发送音频的方法
function _sendAudio(buffer) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(buffer)
  }
}

// 在 return 中添加 _sendAudio
return {
  // ...之前的所有返回值
  _sendAudio,
}
```

- [ ] **Step 6: 验证主界面**

启动后端 `python -m backend.main`，启动前端 `cd frontend && npm run dev`

访问 `http://localhost:5173`，点击"开始同传"：
- 输入会话名 → 点击开始
- 浏览器请求麦克风权限 → 允许
- 状态栏显示"●同传中"和计时器
- 对着麦克风说韩语，验证翻译卡片出现

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: add ClassroomView with StatusBar, TranscriptFeed, NotesPad"
```

---

### Task 13：历史记录页 + 最终集成

**Files:**
- Create: `frontend/src/components/SessionHistory.vue`
- Create: `frontend/src/views/HistoryView.vue`
- Modify: `backend/api/sessions.py` — 补充 segment star 端点

- [ ] **Step 1: 补充 sessions.py 中的 segment star 端点**

在 `backend/api/sessions.py` 末尾添加新路由（需要单独引入）：

```python
# 在 backend/api/sessions.py 末尾追加：

from fastapi import APIRouter as _AR  # 已导入 router，复用即可

segment_router = APIRouter(prefix="/api/segments", tags=["segments"])

class SegmentPatch(BaseModel):
    is_starred: Optional[bool] = None

@segment_router.patch("/{segment_id}")
def patch_segment(segment_id: str, body: SegmentPatch, db: DBSession = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    if body.is_starred is not None:
        seg.is_starred = body.is_starred
    db.commit()
    db.refresh(seg)
    return seg
```

在 `backend/main.py` 中挂载这个新路由：

```python
# 在 main.py 的 include_router 部分添加：
from backend.api.sessions import segment_router
app.include_router(segment_router)
```

- [ ] **Step 2: 写 SessionHistory.vue（列表项组件）**

```vue
<!-- frontend/src/components/SessionHistory.vue -->
<template>
  <div class="history-item" @click="$emit('select', session.id)">
    <div class="info">
      <div class="title">{{ session.name }}</div>
      <div class="meta">
        {{ formatDate(session.started_at) }} · {{ session.duration_seconds ? Math.floor(session.duration_seconds/60) + ' 分钟' : '进行中' }} · {{ session.segment_count }} 条
      </div>
    </div>
    <div class="actions" @click.stop>
      <span class="tag" :class="session.summary ? 'done' : 'pending'">
        {{ session.summary ? '✦ 已总结' : '待总结' }}
      </span>
      <a :href="`/api/sessions/${session.id}/export?format=md`" class="btn-export" download>MD</a>
      <a :href="`/api/sessions/${session.id}/export?format=txt`" class="btn-export" download>TXT</a>
      <button class="btn-delete" @click="$emit('delete', session.id)">删除</button>
    </div>
  </div>
</template>

<script setup>
defineProps(['session'])
defineEmits(['select', 'delete'])
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.history-item {
  padding: 14px 20px; border-bottom: 1px solid #f5f5f5; cursor: pointer;
  display: flex; align-items: center; gap: 16px;
}
.history-item:hover { background: #fafafa; }
.info { flex: 1; }
.title { font-size: 15px; font-weight: 600; }
.meta { font-size: 12px; color: #888; margin-top: 4px; }
.actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.tag { font-size: 11px; padding: 3px 8px; border-radius: 10px; }
.tag.done { background: #e8f5e9; color: #2e7d32; }
.tag.pending { background: #fff3e0; color: #e65100; }
.btn-export { font-size: 12px; padding: 4px 10px; border-radius: 8px; background: #f0f0f5; color: #333; text-decoration: none; }
.btn-delete { font-size: 12px; padding: 4px 10px; border-radius: 8px; background: #fff0f0; color: #ff3b30; border: none; cursor: pointer; }
</style>
```

- [ ] **Step 3: 写 HistoryView.vue**

```vue
<!-- frontend/src/views/HistoryView.vue -->
<template>
  <div class="history-view">
    <div class="header">
      <router-link to="/" class="back-btn">← 返回</router-link>
      <h2>课程记录</h2>
      <input v-model="search" placeholder="搜索会话名..." class="search" />
    </div>

    <div class="list" v-if="!selectedSession">
      <SessionHistory
        v-for="sess in filteredSessions"
        :key="sess.id"
        :session="sess"
        @select="loadSession"
        @delete="deleteSession"
      />
      <div v-if="filteredSessions.length === 0" class="empty">暂无记录</div>
    </div>

    <!-- 详情页 -->
    <div class="detail" v-else>
      <div class="detail-header">
        <button @click="selectedSession = null" class="back-btn">← 返回列表</button>
        <h3>{{ selectedSession.session.name }}</h3>
        <button class="btn-summary" @click="triggerSummary" :disabled="summaryLoading">
          {{ summaryLoading ? '生成中...' : '✦ AI总结' }}
        </button>
      </div>

      <div class="detail-body">
        <div class="segments">
          <div
            v-for="seg in selectedSession.segments"
            :key="seg.id"
            class="seg-card"
            :class="{ starred: seg.is_starred }"
          >
            <span class="seg-ts">{{ formatTs(seg.timestamp_ms) }}</span>
            <div class="seg-ko">{{ seg.ko_text }}</div>
            <div class="seg-zh">{{ seg.zh_text }}</div>
          </div>
        </div>
        <div class="summary-panel" v-if="selectedSession.session.summary">
          <h4>AI 总结</h4>
          <pre class="summary-content">{{ selectedSession.session.summary }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import SessionHistory from '../components/SessionHistory.vue'

const sessions = ref([])
const search = ref('')
const selectedSession = ref(null)
const summaryLoading = ref(false)

const filteredSessions = computed(() =>
  sessions.value.filter(s => s.name.includes(search.value))
)

onMounted(async () => {
  const res = await axios.get('/api/sessions')
  sessions.value = res.data
})

async function loadSession(id) {
  const res = await axios.get(`/api/sessions/${id}`)
  selectedSession.value = res.data
}

async function deleteSession(id) {
  if (!confirm('确认删除此会话？')) return
  await axios.delete(`/api/sessions/${id}`)
  sessions.value = sessions.value.filter(s => s.id !== id)
}

async function triggerSummary() {
  if (!selectedSession.value) return
  summaryLoading.value = true
  try {
    const res = await axios.post(`/api/sessions/${selectedSession.value.session.id}/summary`)
    selectedSession.value.session.summary = res.data.summary
  } finally {
    summaryLoading.value = false
  }
}

function formatTs(ms) {
  if (!ms && ms !== 0) return ''
  const t = Math.floor(ms / 1000)
  return `${Math.floor(t/60).toString().padStart(2,'0')}:${(t%60).toString().padStart(2,'0')}`
}
</script>

<style scoped>
.history-view { display: flex; flex-direction: column; min-height: 100vh; }
.header {
  padding: 16px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 16px; position: sticky; top: 0; z-index: 5;
}
.header h2 { margin: 0; font-size: 18px; }
.back-btn { font-size: 14px; color: #5856d6; text-decoration: none; border: none; background: none; cursor: pointer; }
.search { margin-left: auto; padding: 7px 12px; border: 1px solid #ddd; border-radius: 10px; font-size: 13px; outline: none; }
.empty { text-align: center; padding: 40px; color: #aaa; font-style: italic; }

/* 详情页 */
.detail-header {
  padding: 14px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 16px;
}
.detail-header h3 { margin: 0; flex: 1; font-size: 16px; }
.btn-summary { padding: 7px 14px; background: #5856d6; color: #fff; border: none; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 13px; }
.detail-body { display: flex; gap: 0; flex: 1; overflow: hidden; }
.segments { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.seg-card { padding: 10px 12px; border-radius: 10px; background: #f8f8fc; border-left: 3px solid #5856d6; }
.seg-card.starred { border-left-color: #ff9500; background: #fffcf0; }
.seg-ts { font-size: 11px; color: #c7c7cc; }
.seg-ko { font-size: 14px; font-weight: 600; margin-top: 3px; }
.seg-zh { font-size: 13px; color: #636366; margin-top: 3px; }
.summary-panel { width: 320px; border-left: 1px solid #f0f0f0; padding: 16px; overflow-y: auto; }
.summary-panel h4 { margin: 0 0 12px; font-size: 14px; color: #5856d6; }
.summary-content { font-size: 13px; line-height: 1.7; white-space: pre-wrap; margin: 0; font-family: inherit; }
</style>
```

- [ ] **Step 4: 添加全局基础样式**

```javascript
// frontend/src/main.js — 在末尾添加全局 style
```

在 `frontend/index.html` 的 `<head>` 中添加：
```html
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Inter', sans-serif; background: #f2f2f7; color: #1c1c1e; }
  html, body, #app { height: 100%; }
</style>
```

- [ ] **Step 5: 全流程手动验证**

启动后端：`python -m backend.main`  
启动前端：`cd frontend && npm run dev`

验证清单：
- [ ] 访问 `http://localhost:5173`，点击开始同传，输入会话名
- [ ] 说韩语，确认卡片实时出现（interim → translating → done）
- [ ] 点击☆标记重点，刷新后确认持久化
- [ ] 在笔记区输入文字，1秒后确认"已保存"提示
- [ ] 点击"■ 停止"，访问`/history`，确认会话记录存在
- [ ] 在历史页点击会话，查看详情
- [ ] 点击"AI总结"，等待并查看总结内容
- [ ] 点击"MD"下载，打开确认格式正确
- [ ] 手机浏览器访问（同 WiFi 或 Tailscale），验证移动端 Tab 切换

- [ ] **Step 6: 构建生产版本**

```bash
cd frontend && npm run build
# 生成 frontend/dist/

cd ..
python -m backend.main
# 此时后端直接服务 frontend/dist，访问 http://localhost:8000
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: complete HistoryView with session detail, AI summary, export, and production build"
```

---

## 完成标准

全部任务完成后，以下功能应当正常工作：

| 功能 | 验证方法 |
|------|----------|
| 实时韩语识别（Silero VAD 断句） | 说话停顿 600ms 后触发，长句不被切碎 |
| 实时中文翻译 | 断句后 2-3 秒内出现翻译 |
| 会话持久化 | 刷新页面后历史记录仍存在 |
| AI 总结 | 历史页点击"AI总结"，生成结构化 Markdown |
| 导出 TXT/MD | 下载文件格式正确，含时间戳和翻译 |
| 笔记自动保存 | 输入停止 1 秒后自动 PATCH 到后端 |
| ⭐ 标记重点 | 点击后持久化，历史页显示橙色边框 |
| 移动端适配 | 手机访问显示 Tab 布局，大字体，底部导航 |
| Tailscale 远程访问 | 手机通过 Tailscale HTTPS 访问麦克风可用 |
