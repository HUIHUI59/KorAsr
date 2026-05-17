# backend/asr/model.py
"""Backend-aware ASR model loading.

支持两个后端：
- faster_whisper：CTranslate2 后端，CPU/CUDA 通用，4090 服务器走这个
- mlx：Apple MLX 框架，走 Mac M-series GPU (Metal)，仅 Apple Silicon 可用

通过 settings.asr_backend 切换。get_model() 是统一入口，
返回值类型因后端而异（faster_whisper 返回 WhisperModel 实例；
mlx 返回 HF repo path 字符串，因为 mlx_whisper 内部缓存模型，
调用方按 path_or_hf_repo 调用 transcribe 即可）。
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
from backend.config import settings


# MLX 模型短名 → mlx-community HF repo 映射
# 这些 repo 都是 mlx-community 维护、Apple Silicon 上预转换好的
_MLX_REPO_MAP = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large-v3": "mlx-community/whisper-large-v3",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


_fw_model = None  # type: ignore  # faster_whisper.WhisperModel singleton
_mlx_repo: str | None = None  # mlx 缓存好的 repo 路径


def get_mlx_repo() -> str:
    """返回 mlx-whisper transcribe() 的 path_or_hf_repo 参数值。"""
    name = settings.asr_model
    if name in _MLX_REPO_MAP:
        return _MLX_REPO_MAP[name]
    # 不在映射表里就当成完整 HF repo 名直接用（用户可指定自定义模型）
    return name


def _load_faster_whisper():
    from faster_whisper import WhisperModel
    global _fw_model
    if _fw_model is not None:
        return _fw_model
    threads_info = f", cpu_threads={settings.asr_cpu_threads}" if settings.asr_cpu_threads > 0 else ", cpu_threads=auto"
    print(f"[ASR] Loading faster_whisper {settings.asr_model} on {settings.asr_device}{threads_info}...")
    _fw_model = WhisperModel(
        settings.asr_model,
        device=settings.asr_device,
        compute_type=settings.asr_compute_type,
        cpu_threads=settings.asr_cpu_threads,
    )
    print("[ASR] Model loaded successfully")
    return _fw_model


def _load_mlx():
    """预热 mlx-whisper：第一次 transcribe 会下模型 + JIT 编译，启动时一次性做完。"""
    import mlx_whisper
    global _mlx_repo
    if _mlx_repo is not None:
        return _mlx_repo
    repo = get_mlx_repo()
    print(f"[ASR] Loading mlx-whisper {settings.asr_model} from {repo} (Apple Silicon GPU/Metal)...")
    # 喂一段 1 秒静音，触发模型下载 + 加载 + JIT 编译；返回值丢弃
    warm_audio = np.zeros(16000, dtype=np.float32)
    mlx_whisper.transcribe(warm_audio, path_or_hf_repo=repo, language="ko", verbose=False)
    _mlx_repo = repo
    print("[ASR] Model loaded successfully")
    return _mlx_repo


def get_model():
    """统一入口。返回值类型因后端而异，调用方应通过 transcriber 抽象去用，不直接拿这个对象。"""
    if settings.asr_backend == "mlx":
        return _load_mlx()
    return _load_faster_whisper()
