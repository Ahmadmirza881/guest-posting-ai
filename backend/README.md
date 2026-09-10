# Guest Posting AI — Backend

FastAPI backend, PostgreSQL models, service layer, and CRUD API endpoints for the Guest Posting AI system.

## Project Structure

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application initialization & middleware
│   ├── config.py            # Environment and app configuration
│   ├── database.py          # SQLAlchemy 2.0 engine, Base, SessionLocal & get_db
│   ├── models/              # SQLAlchemy database models
│   │   ├── __init__.py
│   │   ├── user.py          # User entity
│   │   ├── search.py        # Search request entity
│   │   ├── website.py       # Discovered website entity
│   │   ├── search_result.py # SearchResult association entity
│   │   ├── website_analysis.py # Website quality metrics
│   │   └── guest_post.py    # Guest posting detection & guidelines
│   ├── schemas/             # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── search.py        # SearchCreate, SearchResponse, etc.
│   │   └── website.py       # WebsiteDetailResponse, Analysis, etc.
│   ├── services/            # Database repository & service operations
│   │   ├── __init__.py
│   │   ├── search_service.py # Search CRUD operations
│   │   └── website_service.py # Website query operations
│   ├── routes/              # API Route Handlers
│   │   ├── __init__.py
│   │   ├── health.py        # /api/health & /api/health/db
│   │   ├── searches.py      # /api/searches endpoints
│   │   └── websites.py      # /api/websites endpoints
│   └── utils/
│       └── __init__.py
│
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
└── README.md                # Documentation
```

## API Endpoints

### Health Checks
- `GET /api/health` — Non-blocking service health status.
- `GET /api/health/db` — Live PostgreSQL database connectivity check (`SELECT 1`).

### Searches
- `POST /api/searches` — Create a new search query.
- `GET /api/searches` — List past search records with pagination (`?skip=0&limit=50`).
- `GET /api/searches/{id}` — Get full search details with discovered websites, relevance, and quality metrics.

### Websites
- `GET /api/websites` — List discovered websites.
- `GET /api/websites/{id}` — Get website details, quality breakdown scores, and guest posting guidelines.

## Setup & Running

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

### 3. Start Development Server

```bash
uvicorn app.main:app --reload
```

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
