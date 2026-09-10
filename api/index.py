import os
import sys
from pathlib import Path
import secrets

# Ensure current api directory is in Python path
API_DIR = Path(__file__).resolve().parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

# Configure Vercel serverless environment defaults
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/guest_posting_ai.db")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("JWT_SECRET_KEY", "guest-posting-ai-secure-vercel-prod-key-" + secrets.token_hex(16))

# Import FastAPI application
from app.main import app
