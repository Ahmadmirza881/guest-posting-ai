# 🚀 Guest Posting AI — AI-Powered Outreach & Quality Evaluation

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Ahmadmirza881/guest-posting-ai)

**Guest Posting AI** is an intelligent full-stack platform designed to automate guest posting research, evaluate domain authority and quality metrics, inspect editorial guidelines, and rank prospective guest posting opportunities using Gemini AI.

---

## 🌟 Key Features

- **Automated Search**: Search engine integrations (Tavily, SerpApi, Google Custom Search).
- **AI Content Verification**: Powered by Google Gemini (`gemini-2.5-flash`) for relevance scoring and content quality checks.
- **Fast Web Crawler**: Async website crawler with HTML extraction and guidelines detection.
- **Modern UI**: High-performance React 19 SPA built with Vite, Tailwind CSS, and React Router 7.
- **Single-Service Deployment**: Production FastAPI serves compiled React static assets directly with full SPA client-side routing support.
- **Container Ready**: Multi-stage Dockerfile and Docker Compose setup for deployment anywhere.

---

## ⚡ 1-Click Cloud Deployment

Click the button below to automatically deploy the application on Render's free tier:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Ahmadmirza881/guest-posting-ai)

### Required Environment Variables on Render:
- `JWT_SECRET_KEY`: A 32+ character random string for secure JWT tokens.
- `GEMINI_API_KEY`: Your Google Gemini API Key.
- `SEARCH_PROVIDER`: `tavily` (default) or `serpapi`.
- `TAVILY_API_KEY`: Your Tavily API Key.

---

## 🛠️ Local Development & Production Run

### 1. Run in Development Mode:
Double-click `run-all.bat` to launch both the FastAPI backend (port 8000) and Vite frontend (port 5173).

### 2. Run in Production Mode:
Double-click `run-production.bat` to build the React frontend and serve both the UI and API simultaneously on `http://localhost:8000`.

### 3. Docker Run:
```bash
docker compose up -d --build
```
Access the application at `http://localhost:8000`.
