# backend/translation/moonshot.py
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
    """Asynchronously translate Korean text to Chinese. Returns empty string on failure."""
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
