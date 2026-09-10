import os
import sys
from pathlib import Path

# Setup paths so backend modules can be imported
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure Vercel /tmp directory is used for database if running on Vercel
if os.getenv("VERCEL"):
    os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/guest_posting_ai.db")
    os.environ.setdefault("ENVIRONMENT", "production")
    os.environ.setdefault("DEBUG", "False")

from app.main import app
