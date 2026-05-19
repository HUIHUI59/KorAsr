# legacy/ — 旧版本代码归档

这里放的是项目早期的**单文件原型**和**旧前端**，已经被 `backend/` + `frontend/` 的模块化重写取代。
**不要直接运行**这里的文件，它们只保留作历史参考。

如需查找新代码的对应位置，看下表：

| 旧文件 | 旧职责 | 新位置 |
|--------|--------|--------|
| `whisperServerTransVer.py` | 单文件 FastAPI + Faster-Whisper Large-v3 + Moonshot 翻译，最完整的旧版 | `start.py` + `backend/` 整个目录 |
| `whisperServerTransVer copy.py` | 上面那个的备份快照（开发途中手动留的） | — |
| `whisperServerTransVer copy 2.py` | 上面那个的备份快照 2 | — |
| `whisperSever.py` | 用 transformers PyTorch 跑 Whisper Large-v3 Turbo（无翻译） | `backend/asr/model.py` 已支持 turbo |
| `server.py` | 用 FunASR `SenseVoiceSmall` 做识别（无翻译） | 还未在新版集成，若要 A/B 对比可参考此文件 |
| `index.html` | 旧版前端，配 `server.py` 用 | `frontend/` Vue 3 SPA |
| `indexTrans.html` | 旧版前端，配 `whisperServerTransVer.py` 用 | `frontend/` Vue 3 SPA |

## 为什么不直接删？

1. 单文件版本在没有 Vue 构建链的情况下能 5 秒起服务，**应急时可以拿出来跑**
2. `server.py` 是 SenseVoice 集成的现成参考，将来做模型对比时不用从零写
3. 旧 HTML 是无依赖的纯前端，调试 WebSocket 协议时比启动 Vue dev server 快

## 归档时间

2026-05-19，伴随项目目录大整理一起做的。
