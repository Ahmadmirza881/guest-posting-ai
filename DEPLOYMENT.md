# Guest Posting AI — Deployment Guide (تعیناتی گائیڈ)

Yeh guide aapko **Guest Posting AI** project ko production cloud platforms (jaise **Render**, **Railway**, **Vercel**, ya **Docker/VPS**) par deploy karne ka mukammal aur aasan tareeqa faraham karti hai.

---

## 🚀 Deployment Options (Kon sa tareeqa chunein?)

| Option | Platform | Type | Khusoosiyat |
| :--- | :--- | :--- | :--- |
| **Option 1 (Recommended)** | **Render (Free Tier)** | Single Web Service (Docker) | Frontend + Backend aik hi server par, Zero CORS issues, bilkul muft. |
| **Option 2** | **Vercel + Render** | Decoupled | Frontend Vercel ke global CDN par, Backend Render par. |
| **Option 3** | **Railway** | Web Service | Automatic GitHub CI/CD, fast deployment. |
| **Option 4** | **Docker / VPS** | Container | Kisi bhi VPS (DigitalOcean, AWS, Hetzner) par `docker compose up`. |

---

## 📦 Step 0: Project ko GitHub par Push karein

Tamam cloud platforms (Render, Vercel, Railway) GitHub repository se seedha deploy karte hain.

### 1. GitHub par nayi repository banayein:
1. [GitHub](https://github.com/new) par jayein.
2. Repository ka naam rakhein: `guest-posting-ai`.
3. Isko **Public** ya **Private** rakhein (Private behtar hai taake credentials safe rahein).
4. "Initialize this repository with..." ke options ko **uncheck** rehne dein.
5. **Create repository** par click karein.

### 2. Terminal mein yeh commands chalayein:
```bash
# Workspace folder mein:
git remote add origin https://github.com/Ahmadmirza881/guest-posting-ai.git
git branch -M main
git push -u origin main
```

---

## 🌐 Option 1: Render par Deploy karein (Recommended)

Render par aapka Frontend aur Backend dono **aik hi Free Web Service** mein chalte hain via Docker.

### Step-by-Step Tareeqa:
1. [Render Dashboard](https://dashboard.render.com/) par login karein (GitHub ke sath sign in karein).
2. **New +** button par click karein aur **Web Service** select karein.
3. Apni GitHub repository `guest-posting-ai` ko connect karein.
4. Settings mein yeh darj karein:
   - **Name**: `guest-posting-ai`
   - **Region**: Oregon (US West) ya Frankfurt
   - **Runtime / Environment**: **Docker** (Render khud ba khud `Dockerfile` detect kar lega)
   - **Instance Type**: **Free**
5. **Environment Variables** section mein ja kar yeh keys add karein:
   - `ENVIRONMENT` = `production`
   - `DEBUG` = `False`
   - `JWT_SECRET_KEY` = `aik_khoob_lamba_random_secret_32_characters_ka`
   - `GEMINI_API_KEY` = *Aapki Google Gemini API Key*
   - `SEARCH_PROVIDER` = `tavily` (ya `serpapi`)
   - `TAVILY_API_KEY` = *Aapki Tavily API Key* (ya `SEARCH_API_KEY`)
   - `DATABASE_URL` = `sqlite:///./guest_posting_ai.db`
6. **Create Web Service** par click karein!

> ⏱️ **Deployment Time**: Render 2-4 minute mein Node.js se frontend build karega, Python backend configure karega aur live URL provide kar dega (e.g., `https://guest-posting-ai.onrender.com`).

---

## ⚡ Option 2: Vercel (Frontend) + Render (Backend)

Agar aap Frontend ko Vercel ke CDN par aur Backend ko Render par alag alag rakhna chahte hain:

### 1. Backend on Render:
1. Render par **Web Service** banayein.
2. Runtime: **Python 3**.
3. Build Command: `cd backend && pip install -r requirements.txt`.
4. Start Command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Environment Variables mein `ALLOWED_ORIGINS` mein apna Vercel domain shamil karein.

### 2. Frontend on Vercel:
1. [Vercel Dashboard](https://vercel.com/) par jayein aur **Add New > Project** select karein.
2. Apni GitHub repository import karein.
3. **Framework Preset**: Vite select karein.
4. **Environment Variables** mein:
   - `VITE_API_URL` = `https://your-backend.onrender.com/api`
5. **Deploy** par click karein. `vercel.json` already configured hai SPA routing ke liye.

---

## 🚂 Option 3: Railway par Deploy karein

1. [Railway.app](https://railway.app/) par login karein.
2. **New Project** > **Deploy from GitHub repo** select karein.
3. `guest-posting-ai` repository select karein.
4. Railway `Dockerfile` ko detect karke build shuru kar dega.
5. **Variables** tab mein environment variables darj karein.
6. **Networking** tab mein ja kar **Generate Domain** par click karein.

---

## 🐳 Option 4: Docker / Local VPS par Deploy karein

Agar aapke paas apna VPS (Ubuntu / Debian / CentOS) hai:

```bash
# 1. Repository clone karein
git clone https://github.com/Ahmadmirza881/guest-posting-ai.git
cd guest-posting-ai

# 2. Production env file create karein
cp .env.production.example .env

# 3. Docker Compose se launch karein
docker compose up -d --build

# 4. Status check karein
docker compose ps
docker compose logs -f
```
Aapka project `http://your-server-ip:8000` par live ho jayega!

---

## 💻 Local Production Preview (Bina kisi cloud ke test karein)

Aap apne computer par hi production build test kar sakte hain:
1. Root directory mein `run-production.bat` file ko double-click karein.
2. Yeh script frontend build karega aur FastAPI ke zariye `http://localhost:8000` par poora app chala dega.
