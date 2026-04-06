# backend/main.py
import warnings
warnings.filterwarnings("ignore")

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.storage.database import init_db
from backend.api.sessions import router as sessions_router, segment_router
from backend.api.export import router as export_router
from backend.ws.handler import handle_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] Initializing database...")
    init_db()
    from backend.asr.model import get_model
    get_model()
    print("[Startup] Ready")
    yield
    print("[Shutdown] Server stopping")


app = FastAPI(title="korAsr", lifespan=lifespan)

app.include_router(sessions_router)
app.include_router(segment_router)
app.include_router(export_router)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await handle_ws(websocket, session_id)


FRONTEND_DIST = Path("frontend/dist")
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return {"status": "ok", "message": "Backend running. Start frontend: cd frontend && npm run dev"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
