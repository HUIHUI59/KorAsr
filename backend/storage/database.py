# backend/storage/database.py
from typing import Generator

from sqlmodel import SQLModel, create_engine, Session as DBSession
from backend.config import settings

engine = create_engine(settings.database_url, echo=False)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_db() -> Generator[DBSession, None, None]:
    with DBSession(engine) as session:
        yield session
