"""
backend/main.py — Main ASGI application entrypoint for Render and production deployment.

Provides:
  - app: FastAPI application instance (from backend.api)
  - Full-stack support: serves Vite frontend from dist/ when built
"""

import os
import sys

# Ensure repository root and backend directory are in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import the core FastAPI app from backend.api
try:
    from backend.api import app
except ImportError:
    from api import app

# Mount built frontend from dist/ if it exists (for full-stack deployment on Render)
dist_dir = os.path.join(REPO_ROOT, "dist")
if os.path.exists(dist_dir):
    assets_dir = os.path.join(dist_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa_fallback(full_path: str):
        # Do not intercept API or documentation routes
        reserved = ["forecasts", "risk-summary", "metrics", "health", "docs", "openapi.json", "redoc"]
        if full_path in reserved or full_path.startswith("forecast/"):
            return JSONResponse(status_code=404, content={"detail": f"Route '{full_path}' not found"})

        # If a specific static file was requested (e.g. vite.svg, favicon.ico)
        file_path = os.path.join(dist_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Fallback to SPA index.html for client-side routing
        index_file = os.path.join(dist_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)

        return JSONResponse(status_code=404, content={"detail": "Index file not found"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
