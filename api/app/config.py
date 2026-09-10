"""Backend configuration module for Guest Posting AI."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Load environment variables if .env exists
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)
else:
    load_dotenv(override=True)


class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Guest Posting AI API")
    PROJECT_DESCRIPTION: str = "Backend API foundation for the Guest Posting AI platform."
    PROJECT_VERSION: str = "0.1.0"
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

    # Database Configuration
    @property
    def DATABASE_URL(self) -> str:
        env_url = os.getenv("DATABASE_URL")
        if env_url:
            return env_url
        if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
            return "sqlite:////tmp/guest_posting_ai.db"
        return "sqlite:///./guest_posting_ai.db"

    # Allowed CORS Origins
    _origins_raw: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,http://127.0.0.1:5174"
    )

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return [origin.strip() for origin in self._origins_raw.split(",") if origin.strip()]

    # Frontend Static Serving Configuration
    SERVE_FRONTEND: bool = os.getenv("SERVE_FRONTEND", "True").lower() in ("true", "1", "yes")

    @property
    def FRONTEND_DIST_DIR(self) -> Path:
        custom_path = os.getenv("FRONTEND_DIST_DIR")
        if custom_path:
            return Path(custom_path)
        # Check parent dist directory (standard monorepo / local)
        candidate = BASE_DIR.parent / "dist"
        if candidate.exists():
            return candidate
        # Check backend/dist or backend/static directory (container build)
        for sub in ("dist", "static"):
            alt = BASE_DIR / sub
            if alt.exists():
                return alt
        return candidate

    # Search Engine Provider Configuration (Step 10)
    SEARCH_PROVIDER: str = os.getenv("SEARCH_PROVIDER", "tavily").lower()
    SEARCH_API_KEY: str | None = os.getenv("SEARCH_API_KEY", None)
    TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY", None)
    SEARCH_ENGINE_ID: str | None = os.getenv("SEARCH_ENGINE_ID", None)
    SEARCH_TIMEOUT_SECONDS: float = float(os.getenv("SEARCH_TIMEOUT_SECONDS", "15.0"))

    # Website Crawler Configuration (Step 12)
    CRAWLER_USER_AGENT: str = os.getenv(
        "CRAWLER_USER_AGENT",
        "GuestPostingAI/1.0 (+https://github.com/guest-posting-ai)"
    )
    CRAWLER_TIMEOUT_SECONDS: float = float(os.getenv("CRAWLER_TIMEOUT_SECONDS", "15.0"))
    CRAWLER_MAX_RESPONSE_BYTES: int = int(os.getenv("CRAWLER_MAX_RESPONSE_BYTES", "2097152"))  # 2MB
    CRAWLER_MAX_REDIRECTS: int = int(os.getenv("CRAWLER_MAX_REDIRECTS", "5"))

    # AI Verification / Gemini Configuration (Step 15)
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY", None)
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_TIMEOUT_SECONDS: float = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30.0"))

    # Authentication & Security Configuration (Step 21 & 25)
    DEV_DEFAULT_JWT_SECRET: str = "guest-posting-ai-insecure-dev-secret-key-change-in-production-32bytes"
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "guest-posting-ai-insecure-dev-secret-key-change-in-production-32bytes"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str | None = os.getenv("GOOGLE_CLIENT_ID", None)
    GOOGLE_CLIENT_SECRET: str | None = os.getenv("GOOGLE_CLIENT_SECRET", None)

    # Parallel Processing / Concurrency Configuration (Step 23)
    MAX_CONCURRENT_WEBSITES: int = int(os.getenv("MAX_CONCURRENT_WEBSITES", "5"))
    PIPELINE_DEFAULT_CONCURRENCY: int = int(os.getenv("PIPELINE_DEFAULT_CONCURRENCY", "5"))
    PIPELINE_MAX_CONCURRENCY_LIMIT: int = int(os.getenv("PIPELINE_MAX_CONCURRENCY_LIMIT", "20"))

    # Caching, Rate Limiting & Retry Configuration (Step 24)
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "True").lower() in ("true", "1", "yes")
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "1000"))
    MAX_CONCURRENT_HTTP_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_HTTP_REQUESTS", "10"))
    MAX_CONCURRENT_AI_REQUESTS: int = int(os.getenv("MAX_CONCURRENT_AI_REQUESTS", "3"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_BASE_DELAY_SECONDS: float = float(os.getenv("RETRY_BASE_DELAY_SECONDS", "1.0"))
    RETRY_MAX_DELAY_SECONDS: float = float(os.getenv("RETRY_MAX_DELAY_SECONDS", "10.0"))

    def validate_security(self) -> None:
        """Enforce strict production security constraints."""
        is_production = self.ENVIRONMENT == "production" or not self.DEBUG
        if is_production:
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == self.DEV_DEFAULT_JWT_SECRET or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "Production security error: JWT_SECRET_KEY must be configured with a secure, "
                    "non-default secret of at least 32 characters in production."
                )


settings = Settings()

