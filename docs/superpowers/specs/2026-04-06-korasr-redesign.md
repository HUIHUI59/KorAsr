# korAsr 完整重写设计文档

**日期**: 2026-04-06  
**项目**: korAsr — 实时韩语语音识别 + 中文翻译  
**方案**: 完整重写（Vue 3 + FastAPI 模块化）  

---

## 1. 背景与目标

### 使用场景
用户在韩国留学，需要在以下场景中实时识别韩语并翻译为中文：
- 大学课堂（教授单人讲课，持续 45–90 分钟）
- 与教授的一对一面谈（对话场景）

### 核心痛点（现有代码）
| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 长句被切碎 | RMS 能量阈值 VAD 误判停顿 | 引入 Silero VAD ML 模型 |
| 代码不规范 | 配置硬编码、无模块化、无错误处理 | 完整重写，模块化架构 |
| 无内容保存 | 无数据库 | SQLite 持久化存储 |
| 无课后复习 | 无历史功能 | 历史记录页 + AI 总结 |
| 移动端体验差 | 非响应式布局 | Vue 3 响应式 SPA |

### 目标
- 桌面端 + 手机端双端流畅使用（通过 Tailscale VPN 远程访问）
- 断句精度显著提升（Silero VAD 替代 RMS 阈值）
- 每节课自动保存，课后可导出 + AI 生成结构化总结
- 代码规范、可维护、便于后续扩展

---

## 2. 系统架构

### 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + uvicorn |
| ASR 引擎 | Faster-Whisper Large-v3（CUDA fp16）|
| VAD | Silero VAD（PyTorch）|
| 翻译 API | Moonshot（moonshot-v1-8k）|
| 数据库 | SQLite + SQLModel（ORM）|
| 前端框架 | Vue 3 + Vite |
| 状态管理 | Pinia |
| 网络访问 | Tailscale（自动 HTTPS，麦克风权限无障碍）|

### 目录结构

```
korAsr/
├── backend/
│   ├── main.py                  # FastAPI 应用入口，挂载路由和静态文件
│   ├── config.py                # 从 .env 读取所有配置项
│   ├── asr/
│   │   ├── model.py             # Faster-Whisper 模型单例加载
│   │   ├── vad.py               # Silero VAD 封装，逐帧语音概率检测
│   │   └── transcriber.py       # 转录逻辑：VAD 调度 + Whisper 推理
│   ├── translation/
│   │   └── moonshot.py          # Moonshot API 异步翻译封装
│   ├── storage/
│   │   ├── database.py          # SQLite 连接 + SQLModel 初始化
│   │   └── models.py            # ORM 模型：Session, Segment
│   ├── summary/
│   │   └── generator.py         # 课后 AI 总结：调用 Moonshot 生成结构化笔记
│   ├── ws/
│   │   └── handler.py           # WebSocket 连接管理 + 音频调度主循环
│   └── api/
│       ├── sessions.py          # REST: 会话 CRUD，AI 总结触发
│       └── export.py            # REST: 导出 TXT / Markdown
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TranscriptFeed.vue    # 实时翻译卡片流（含状态动画）
│   │   │   ├── NotesPad.vue          # 右侧笔记区（桌面端）/ Tab 页（移动端）
│   │   │   ├── StatusBar.vue         # 连接状态、会话计时器、会话命名
│   │   │   └── SessionHistory.vue    # 历史记录列表项
│   │   ├── views/
│   │   │   ├── ClassroomView.vue     # 主界面：实时同传
│   │   │   └── HistoryView.vue       # 历史记录 + AI 总结 + 导出
│   │   ├── stores/
│   │   │   └── session.js            # Pinia：WebSocket 连接、翻译片段、笔记
│   │   ├── router/
│   │   │   └── index.js              # Vue Router：/ 和 /history
│   │   └── App.vue
│   ├── package.json
│   └── vite.config.js               # 代理 /api 和 /ws 到后端 8000 端口
├── .env                             # 所有配置（不提交 git）
├── .env.example                     # 配置模板（提交 git）
├── requirements.txt
└── README.md
```

---

## 3. VAD + ASR 精度方案

### 问题根源
现有代码用 `np.sqrt(np.mean(chunk**2)) < 0.012` 判断静音，存在：
- 说话中的自然停顿（换气、思考）被误判为句子结束
- 背景噪声导致阈值不稳定
- 无法感知语音"语义边界"

### 解决方案：Silero VAD

```python
# vad.py 核心逻辑
import torch

class SileroVAD:
    def __init__(self, threshold=0.5, min_speech_ms=250, min_silence_ms=600):
        self.model, self.utils = torch.hub.load(
            'snakers4/silero-vad', 'silero_vad', force_reload=False
        )
        self.threshold = threshold        # 语音概率阈值
        self.min_speech_ms = min_speech_ms   # 最短语音段（过滤噪声）
        self.min_silence_ms = min_silence_ms # 静音多久才算断句（关键参数）
        self._reset()
    
    def process_chunk(self, chunk: np.ndarray) -> dict:
        """返回 {'speech_prob': float, 'is_end': bool}"""
        prob = self.model(torch.from_numpy(chunk), 16000).item()
        # ... 状态机逻辑：累积静音时长，超过 min_silence_ms 才触发 is_end
```

**关键改进**：
- `min_silence_ms=600`：600ms 以上的静音才断句，自然停顿不会误切
- 语音概率 > 0.5 才算"说话中"，抗噪
- 最长 8 秒强制断句（`MAX_BUFFER_S=8.0`，比现在的 6 秒更宽松）

---

## 4. 数据模型

```python
# storage/models.py

class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str                          # 用户命名（如"경제학개론 4월 6일"）
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    segment_count: int = 0
    summary: Optional[str]            # AI 生成的总结（Markdown 格式）
    notes: Optional[str]              # 用户手写笔记
    segments: List["Segment"] = Relationship(back_populates="session")

class Segment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    sequence: int                      # 段落序号
    timestamp_ms: int                  # 距会话开始的毫秒数
    ko_text: str                       # 韩语识别结果
    zh_text: Optional[str]             # 中文翻译
    is_starred: bool = False           # 用户标记重点
    session: Optional[Session] = Relationship(back_populates="segments")
```

---

## 5. API 设计

### WebSocket

| 端点 | 描述 |
|------|------|
| `WS /ws/{session_id}` | 音频流输入，JSON 消息输出 |

**连接流程**：
1. 前端先 `POST /api/sessions` 创建会话，获得 `session_id`
2. 用 `session_id` 建立 WebSocket：`ws://host/ws/{session_id}`
3. 断开时服务端自动更新 `ended_at` 和 `duration_seconds`

**下行消息格式**（服务器 → 前端）：
```json
{ "id": "<segment_uuid>", "status": "interim|translating|done", "ko": "...", "zh": "...", "timestamp_ms": 12300 }
```

### REST API

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/sessions` | 创建新会话，返回 session_id |
| GET | `/api/sessions` | 获取历史会话列表 |
| GET | `/api/sessions/{id}` | 获取会话详情（含所有 segments）|
| PATCH | `/api/sessions/{id}` | 更新会话名称或笔记 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| POST | `/api/sessions/{id}/summary` | 触发 AI 总结生成（异步）|
| GET | `/api/sessions/{id}/export` | 导出（query: `format=txt\|md`，见下方格式说明）|
| PATCH | `/api/segments/{id}` | 更新 segment（is_starred）|

---

## 6. 前端设计

### ClassroomView（主界面）

**桌面端（≥768px）**：
- 左侧 65%：`TranscriptFeed`，翻译卡片流，自动滚动到底部
- 右侧 35%：`NotesPad`，Markdown 文本框，失焦自动 PATCH 到后端
- 顶部 `StatusBar`：连接状态点、会话名（可点击修改）、计时器、停止按钮、AI 总结按钮

**移动端（<768px）**：
- 全屏 `TranscriptFeed`
- 底部 Tab 栏：翻译 / 笔记 / 历史
- 大红圆形按钮：停止录音
- `NotesPad` 在"笔记"Tab 内

**翻译卡片三态**：
| 状态 | 样式 |
|------|------|
| `interim` | 橙色左边框，中文显示"识别中..." |
| `translating` | 紫色左边框，中文显示脉冲动画"翻译中..." |
| `done` | 紫色左边框，韩+中全部显示，右上⭐可点击 |

### HistoryView（历史记录页）

- 会话列表，按日期倒序
- 每行：会话名、时长、片段数、是否有 AI 总结、导出按钮
- 点击展开：查看完整翻译记录 + 总结
- 顶部搜索框：按关键词过滤

### 导出格式

**TXT**：纯文本，每行一段，格式为 `[mm:ss] 韩语原文 | 中文翻译`

**Markdown**：
```markdown
# 경제학개론 — 2026-04-06

## 原始记录

| 时间 | 韩语 | 中文翻译 |
|------|------|----------|
| 00:21 | 오늘은 케인즈... | 今天我们来看... |

## AI 总结
（总结内容，若已生成）

## 我的笔记
（用户手写笔记，若有）
```

---

### AI 总结格式（Moonshot 输出）

```markdown
## 课程总结：경제학개론 (2026-04-06)

### 主要内容
1. 有效需求理论的定义与背景
2. 与古典经济学的核心区别
3. 投资乘数效应

### 关键概念
- **유효수요 (有效需求)**：有购买力支撑的实际需求
- **승수효과 (乘数效应)**：投资变动引发多倍产出变动

### 重点句子
> "시장은 항상 균형을 찾지 않는다" — 市场并不总是会找到均衡

### 待跟进
- [ ] 查阅凯恩斯《就业、利息和货币通论》第3章
```

---

## 7. 配置管理

```ini
# .env.example
MOONSHOT_API_KEY=sk-...

# ASR 参数
ASR_MODEL=large-v3
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_BEAM_SIZE=5
ASR_MAX_BUFFER_S=8.0
ASR_MIN_BUFFER_S=0.5

# VAD 参数
VAD_THRESHOLD=0.5
VAD_MIN_SILENCE_MS=600
VAD_MIN_SPEECH_MS=250

# 幻觉黑名单（逗号分隔）
HALLUCINATION_BLACKLIST=자막,감사합니다,시청해주셔서,구독,좋아요
```

---

## 8. 部署方案

### 网络访问（Tailscale）
1. 4090 服务器安装 Tailscale，加入用户的 Tailnet
2. 手机和笔记本也安装 Tailscale
3. 在 Tailscale 管理后台（admin.tailscale.com → DNS）开启 **HTTPS Certificates**，否则浏览器会拒绝麦克风权限
4. 访问地址：`https://<machine-name>.tail<hash>.ts.net:8000`
5. 服务器端用 `uvicorn` 监听 `0.0.0.0:8000`

### 启动脚本
```bash
# 启动后端
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

# 开发时启动前端（代理到后端）
cd frontend && npm run dev
```

---

## 9. 范围界定

### 本次包含（v1）
- Silero VAD 断句精度优化
- 后端模块化重构（5 个模块）
- SQLite 会话 + 段落存储
- Vue 3 响应式前端（主界面 + 历史页）
- AI 课后总结（Moonshot）
- 导出 TXT / Markdown
- ⭐ 重点标记

### 明确不包含（v1 不做）
- 多语言翻译目标（只做韩→中）
- 说话人识别（diarization）
- 离线模式
- 用户账户系统
- 移动端 App（只做 Web）
