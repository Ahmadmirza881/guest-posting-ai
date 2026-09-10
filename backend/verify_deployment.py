import asyncio
import httpx
from app.main import app

async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        r_health = await client.get("/api/health")
        print(f"[TEST 1] Health Check: {r_health.status_code} - {r_health.json()}")

        r_root = await client.get("/")
        has_root_1 = '<div id="root">' in r_root.text
        print(f"[TEST 2] Root SPA: {r_root.status_code} - Has Root: {has_root_1}")

        r_spa = await client.get("/search")
        has_root_2 = '<div id="root">' in r_spa.text
        print(f"[TEST 3] SPA /search: {r_spa.status_code} - Has Root: {has_root_2}")

        r_404 = await client.get("/api/nonexistent")
        print(f"[TEST 4] API 404 Route: {r_404.status_code} - Body: {r_404.json()}")

if __name__ == "__main__":
    asyncio.run(main())
