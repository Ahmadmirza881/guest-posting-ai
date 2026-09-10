from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Guest Posting AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "guest-posting-ai-backend",
        "platform": "vercel-serverless"
    }

@app.get("/api")
def api_root():
    return {
        "service": "guest-posting-ai",
        "status": "online",
        "docs": "/docs"
    }
