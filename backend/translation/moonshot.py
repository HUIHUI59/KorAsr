# backend/translation/moonshot.py
from typing import AsyncIterator
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
    """Asynchronously translate Korean text to Chinese. Returns empty string on failure.

    一次性返回完整译文，适合非实时场景（精修管道、batch 翻译等）。
    实时管道走 translate_stream() 拿到流式增量。
    """
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
        print(f"[Translation] Error: {e}")
        return ""


async def translate_stream(text: str) -> AsyncIterator[str]:
    """Stream tokens from Moonshot. Yields delta strings (NOT cumulative).

    用法：
        accumulated = ""
        async for delta in translate_stream(ko):
            accumulated += delta
            # push partial accumulated to frontend

    出错时静默结束（与 translate() 行为一致），调用方据 accumulated 判断是否成功。
    诊断日志会打印：首 token 延迟、总 token 数、总耗时，便于判断慢在 Moonshot 还是本地。
    """
    import time as _time
    if not text or len(text) < 2:
        return
    t_start = _time.perf_counter()
    t_first_token = None
    n_chunks = 0
    total_chars = 0
    try:
        client = get_client()
        stream = await client.chat.completions.create(
            model="moonshot-v1-auto",  # 自动路由到当前最空闲池，比固定 v1-8k 抗拥堵
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                if t_first_token is None:
                    t_first_token = _time.perf_counter()
                n_chunks += 1
                total_chars += len(delta)
                yield delta
        t_end = _time.perf_counter()
        ttft = (t_first_token - t_start) if t_first_token else -1
        total = t_end - t_start
        print(
            f"[Translation] OK total={total:.2f}s ttft={ttft:.2f}s "
            f"chunks={n_chunks} chars={total_chars} input_len={len(text)}"
        )
    except Exception as e:
        print(f"[Translation] Stream error: {e}")
        return
