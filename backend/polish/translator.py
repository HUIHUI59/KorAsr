# backend/polish/translator.py
"""精修管道：每 60s 用长稿 ASR 重识别 + LLM 重译。

跟实时管道（5-8s 切片，translate_stream）的区别：
- 实时：每段独立 ASR + 独立翻译，求快，断句受 5-8s 上限影响
- 精修：长稿 ASR（让 Whisper 自己分句，质量高很多）+ LLM 整稿翻译（术语一致）
"""
import time
import numpy as np

from backend.translation.moonshot import get_client
from backend.config import settings
from backend.asr.model import get_mlx_repo

POLISH_SYSTEM_PROMPT = (
    "你是一位专业的韩中同传翻译，正在为留学生整理课堂内容。\n"
    "下面是过去 60 秒的韩文录音转写（已经经过整稿 ASR 重新识别，质量较高）。\n"
    "请将其翻译成自然、流畅、术语一致的中文。\n\n"
    "要求：\n"
    "1. 跨段术语保持一致（同一个韩文词组在全段译成同一个中文词）\n"
    "2. 自然分段（按语义而非长度）\n"
    "3. 直接输出最终中文，不要任何解释、不要列表、不要重复韩文\n"
    "4. 保留原文的语气（讲解、提问、感叹等）"
)


def transcribe_long_form(audio: np.ndarray) -> str:
    """对一段较长音频（通常 60s 左右）做长稿 Whisper 识别。

    跟 transcribe_audio() 的区别：
    - 不带 RMS 门、prompt-echo / 黑名单等过滤（长稿天然有变化，过滤会误伤）
    - condition_on_previous_text=True（长稿内 segments 互相关联，提升连贯性）
    - 由 Whisper 自己做内部分句（远优于上游 5-8s VAD 切片）
    """
    if settings.asr_backend == "mlx":
        import mlx_whisper
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=get_mlx_repo(),
            language="ko",
            temperature=0.0,
            condition_on_previous_text=True,
            initial_prompt=settings.asr_initial_prompt or None,
            no_speech_threshold=settings.asr_no_speech_threshold,
            verbose=False,
        )
        return result["text"].strip()
    # faster_whisper fallback（4090 服务器）
    from backend.asr.model import get_model
    model = get_model()
    segments, _ = model.transcribe(
        audio,
        language="ko",
        beam_size=settings.asr_beam_size,
        temperature=0.0,
        condition_on_previous_text=True,
        initial_prompt=settings.asr_initial_prompt or None,
        no_speech_threshold=settings.asr_no_speech_threshold,
        compression_ratio_threshold=settings.asr_compression_ratio_threshold,
        log_prob_threshold=settings.asr_log_prob_threshold,
    )
    return "".join(seg.text for seg in segments).strip()


async def polish_translate(ko_text: str) -> str:
    """对一段长稿韩文做 LLM 整稿翻译，返回连贯的中文段落。

    出错返回空串（调用方可决定是否回退）。
    """
    if not ko_text or len(ko_text) < 2:
        return ""
    user_prompt = f"韩文原文：\n{ko_text}\n\n请输出中文译文："
    t0 = time.perf_counter()
    try:
        client = get_client()
        completion = await client.chat.completions.create(
            model="moonshot-v1-auto",   # 自动路由，抗 v1-8k 拥堵
            messages=[
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        text = completion.choices[0].message.content.strip()
        elapsed = time.perf_counter() - t0
        print(f"[Polish] LLM OK input={len(ko_text)} chars elapsed={elapsed:.2f}s out={len(text)} chars")
        return text
    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"[Polish] LLM Error after {elapsed:.2f}s: {e}")
        return ""
