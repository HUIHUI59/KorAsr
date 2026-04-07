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
