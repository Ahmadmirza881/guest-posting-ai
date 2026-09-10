import os
import sys
import logging
from pathlib import Path
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vercel_handler")

# Set up paths so app package is importable
API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Serverless environment overrides (writable /tmp directory)
if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ["DATABASE_URL"] = "sqlite:////tmp/guest_posting_ai.db"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "False"
    os.environ.setdefault("JWT_SECRET_KEY", "guest-posting-ai-secure-vercel-prod-key-" + secrets.token_hex(16))

try:
    from app.main import app
except Exception as e:
    import traceback
    logger.exception(f"FastAPI app import error on Vercel: {e}")
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI()

    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def error_fallback(path_name: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "FastAPI initialization failed on Vercel",
                "message": str(e),
                "traceback": traceback.format_exc()
            }
        )
