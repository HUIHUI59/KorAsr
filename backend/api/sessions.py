# backend/api/sessions.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session as DBSession, select
from pydantic import BaseModel

from backend.storage.database import get_db
from backend.storage.models import Session as SessionModel, Segment
from backend.summary.generator import generate_summary

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
segment_router = APIRouter(prefix="/api/segments", tags=["segments"])


class SessionCreate(BaseModel):
    name: str


class SessionUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None


class SegmentPatch(BaseModel):
    is_starred: Optional[bool] = None


@router.post("", status_code=201)
def create_session(body: SessionCreate, db: DBSession = Depends(get_db)):
    sess = SessionModel(name=body.name)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


@router.get("")
def list_sessions(db: DBSession = Depends(get_db)):
    sessions = db.exec(
        select(SessionModel).order_by(SessionModel.started_at.desc())
    ).all()
    return sessions


@router.get("/{session_id}")
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment)
        .where(Segment.session_id == session_id)
        .order_by(Segment.sequence)
    ).all()
    return {"session": sess, "segments": segments}


@router.patch("/{session_id}")
def update_session(session_id: str, body: SessionUpdate, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if body.name is not None:
        sess.name = body.name
    if body.notes is not None:
        sess.notes = body.notes
    db.commit()
    db.refresh(sess)
    return sess


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    for seg in db.exec(select(Segment).where(Segment.session_id == session_id)).all():
        db.delete(seg)
    db.delete(sess)
    db.commit()


@router.post("/{session_id}/summary")
async def trigger_summary(session_id: str, db: DBSession = Depends(get_db)):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment).where(Segment.session_id == session_id).order_by(Segment.sequence)
    ).all()
    summary = await generate_summary(list(segments))
    sess.summary = summary
    db.commit()
    return {"summary": summary}


@segment_router.patch("/{segment_id}")
def patch_segment(segment_id: str, body: SegmentPatch, db: DBSession = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "Segment not found")
    if body.is_starred is not None:
        seg.is_starred = body.is_starred
    db.commit()
    db.refresh(seg)
    return seg
