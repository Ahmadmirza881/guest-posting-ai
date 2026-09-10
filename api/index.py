import os
import sys
from pathlib import Path
import secrets

# Set up module resolution
API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import _app
sys.modules["app"] = _app

# Vercel serverless environment defaults
if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ["DATABASE_URL"] = "sqlite:////tmp/guest_posting_ai.db"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "False"
    os.environ.setdefault("JWT_SECRET_KEY", "guest-posting-ai-secure-vercel-prod-key-" + secrets.token_hex(16))

from _app.main import app

# Top-level entrypoints for Vercel AST parser
app = app
handler = app
