"""
FastAPI application for Trend Intelligence Hub.
"""
import json
import os
from typing import Any
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles


class UTF8JSONResponse(JSONResponse):
    """
    JSONResponse that always sets charset=utf-8 and uses ensure_ascii=False,
    so Cyrillic/Ukrainian text renders correctly in the browser without mojibake.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# Load .env before anything reads os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.api.routes import status, me, projects, monitors, runs, presets, sources

app = FastAPI(
    title="Trend Intelligence Hub API",
    description="Backend API for the Trend Intelligence Hub Telegram Mini App",
    version="6.0.1",
    default_response_class=UTF8JSONResponse,
)

# CORS - allow Telegram WebApp and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
prefix = "/api"
app.include_router(status.router,   prefix=prefix, tags=["status"])
app.include_router(me.router,       prefix=prefix, tags=["me"])
app.include_router(projects.router, prefix=prefix, tags=["projects"])
app.include_router(monitors.router, prefix=prefix, tags=["monitors"])
app.include_router(runs.router,     prefix=prefix, tags=["runs"])
app.include_router(presets.router,  prefix=prefix, tags=["presets"])
app.include_router(sources.router,  prefix=prefix, tags=["sources"])

# Serve Mini App static files at /webapp
_webapp_dir = os.path.join(os.path.dirname(__file__), "..", "webapp")
_webapp_dir = os.path.normpath(_webapp_dir)

if os.path.isdir(_webapp_dir):
    app.mount("/webapp", StaticFiles(directory=_webapp_dir, html=True), name="webapp")

    @app.get("/")
    async def root():
        index = os.path.join(_webapp_dir, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return {"message": "Trend Intelligence Hub API", "docs": "/docs", "webapp": "/webapp"}
else:
    @app.get("/")
    async def root():
        return {"message": "Trend Intelligence Hub API v6.0", "docs": "/docs"}


# Init DB on startup
@app.on_event("startup")
async def startup_event():
    try:
        from storage import database as db
        db.init_db()
        from config_loader import seed_system_presets
        seed_system_presets()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Startup init failed: {e}")
