"""Vercel Serverless Function entry point for Guest Posting AI API."""

import os
import sys
import tempfile
from pathlib import Path

# Configure paths
_current_dir = Path(__file__).resolve().parent
_app_dir = _current_dir / "_app"

if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

# Ensure writable SQLite database in serverless /tmp
if not os.getenv("DATABASE_URL"):
    _tmp_db = Path(tempfile.gettempdir()) / "guest_posting_ai.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.as_posix()}"

# Ensure fallback JWT secret if none is set so startup checks pass
if not os.getenv("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "guest-posting-ai-production-serverless-jwt-secret-key-32bytes-min"

# Alias _app to app for internal module imports
import _app
sys.modules["app"] = _app

# Pre-import models and initialize DB tables so serverless cold starts have all tables ready
from app.database import init_db
import app.models

try:
    init_db()
except Exception as e:
    print(f"Database initialization deferred or warning: {e}")

from app.main import app

# Top-level handler and app assignments for Vercel AST parser
handler = app
app = app
