import os
import sys
from pathlib import Path

# Setup paths so backend modules can be imported
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure Vercel /tmp directory and secure keys are used if running on Vercel
if os.getenv("VERCEL"):
    import secrets
    os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/guest_posting_ai.db")
    os.environ.setdefault("ENVIRONMENT", "production")
    os.environ.setdefault("DEBUG", "False")
    if not os.getenv("JWT_SECRET_KEY") or len(os.getenv("JWT_SECRET_KEY", "")) < 32:
        os.environ["JWT_SECRET_KEY"] = "guest-posting-ai-secure-vercel-prod-key-" + secrets.token_hex(16)

from app.main import app
