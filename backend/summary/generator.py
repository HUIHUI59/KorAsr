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
        print(f"[Summary] Error: {e}")
        return ""
