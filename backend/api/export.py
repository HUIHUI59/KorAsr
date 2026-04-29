# backend/api/export.py
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import Session as DBSession, select

from backend.storage.database import get_db
from backend.storage.models import Session as SessionModel, Segment

router = APIRouter(prefix="/api/sessions", tags=["export"])


def _content_disposition(filename: str) -> str:
    """Build Content-Disposition with RFC 5987 UTF-8 encoding for non-ASCII filenames."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


@router.get("/{session_id}/export")
def export_session(
    session_id: str,
    format: str = "txt",
    db: DBSession = Depends(get_db),
):
    sess = db.get(SessionModel, session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    segments = db.exec(
        select(Segment)
        .where(Segment.session_id == session_id)
        .order_by(Segment.sequence)
    ).all()

    if format == "txt":
        lines = [f"# {sess.name}", f"# {sess.started_at.strftime('%Y-%m-%d %H:%M')}", ""]
        for seg in segments:
            mm = seg.timestamp_ms // 1000 // 60
            ss = seg.timestamp_ms // 1000 % 60
            lines.append(f"[{mm:02d}:{ss:02d}] {seg.ko_text} | {seg.zh_text or ''}")
        if sess.notes:
            lines += ["", "=== My Notes ===", sess.notes]
        content = "\n".join(lines)
        return PlainTextResponse(
            content=content,
            headers={"Content-Disposition": _content_disposition(f"{sess.name}.txt")},
        )

    elif format == "md":
        lines = [
            f"# {sess.name}",
            f"**Date**: {sess.started_at.strftime('%Y-%m-%d')}  ",
            f"**Duration**: {sess.duration_seconds // 60 if sess.duration_seconds else 0} min  ",
            f"**Segments**: {sess.segment_count}",
            "",
            "## Original Transcript",
            "",
            "| Time | Korean | Chinese |",
            "|------|--------|---------|",
        ]
        for seg in segments:
            mm = seg.timestamp_ms // 1000 // 60
            ss = seg.timestamp_ms // 1000 % 60
            star = "⭐ " if seg.is_starred else ""
            lines.append(f"| {mm:02d}:{ss:02d} | {star}{seg.ko_text} | {seg.zh_text or ''} |")

        if sess.summary:
            lines += ["", "## AI Summary", "", sess.summary]
        if sess.notes:
            lines += ["", "## My Notes", "", sess.notes]

        content = "\n".join(lines)
        return PlainTextResponse(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": _content_disposition(f"{sess.name}.md")},
        )

    raise HTTPException(400, "format must be 'txt' or 'md'")
