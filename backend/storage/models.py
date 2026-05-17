# backend/storage/models.py
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4


class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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


class PolishedChunk(SQLModel, table=True):
    """每 60 秒一次的精修批次：把同一窗口内的 segments 拼起来送 LLM 重译。

    chunk_index 从 0 起递增，对应第 N 个 60 秒窗口。
    start/end_segment_seq 标记本窗口包含哪些 segments，便于回溯。
    """
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    chunk_index: int
    start_segment_seq: int
    end_segment_seq: int
    ko_combined: str         # 合并后的韩文原文（按 sequence 顺序）
    zh_polished: str         # LLM 重译后的中文（自然分段、术语一致）
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
