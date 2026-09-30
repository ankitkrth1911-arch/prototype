"""
backend/main.py — Main ASGI application entrypoint for Render and production deployment.

Provides:
  - app: FastAPI application instance (from backend.api)
  - Static file mounting: serves Vite frontend from dist/ when built
  - SPA catch-all routing for client-side navigation
"""

import os
import sys
import logging
from pathlib import Path

from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger("uvicorn.error")

# Determine paths relative to this file (not the working directory)
MAIN_FILE = Path(__file__).resolve()
BASE_DIR = MAIN_FILE.parent  # backend/
REPO_ROOT = BASE_DIR.parent  # repository root

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import core FastAPI app with /api routes from backend.api
try:
    from backend.api import app
except ImportError:
    from api import app

DIST_DIR = REPO_ROOT / "dist"
INDEX_FILE = DIST_DIR / "index.html"
ASSETS_DIR = DIST_DIR / "assets"

# Check if dist/ folder exists
if DIST_DIR.exists() and INDEX_FILE.exists():
    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
        logger.info(f"[main.py] Mounted assets folder from {ASSETS_DIR}")

    # Catch-all route registered AFTER all API routes for SPA routing and refresh
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Do not intercept any API or docs paths
        if (
            full_path.startswith("api")
            or full_path in ["health", "docs", "openapi.json", "redoc"]
            or full_path.startswith("forecast/")
            or full_path in ["forecasts", "risk-summary", "metrics"]
        ):
            return JSONResponse(status_code=404, content={"detail": f"Not Found: /{full_path}"})

        # If a specific static file directly in dist exists (e.g., favicon.ico, vite.svg)
        target_file = DIST_DIR / full_path
        if full_path and target_file.is_file():
            return FileResponse(str(target_file))

        # SPA fallback: return index.html for client-side routes (and root "/")
        return FileResponse(str(INDEX_FILE))
else:
    logger.warning(
        f"[main.py] WARNING: Frontend dist folder not found at '{DIST_DIR}'. "
        "The frontend UI will not be served. Ensure the Build Command runs 'npm install && npm run build'."
    )

    @app.get("/")
    def root_build_missing():
        return {
            "system": "BRICS Healthcare AI",
            "status": "warning",
            "message": "Frontend build not found at dist/. Please ensure your build command runs 'npm install && npm run build'.",
            "api_status": "/api/status",
            "health": "/health"
        }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
