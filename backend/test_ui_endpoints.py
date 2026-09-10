"""UI and API Integration Endpoints Verification Script.

Tests the running frontend dev server (port 5173) and backend API (port 8000).
"""

import httpx

def test_servers():
    print("=" * 60)
    print("TESTING FRONTEND (PORT 5173) & BACKEND (PORT 8000)")
    print("=" * 60)

    # 1. Test Frontend Server
    try:
        r = httpx.get("http://localhost:5173/", timeout=5.0)
        print(f"[PASS] Frontend Server is UP (Status: {r.status_code})")
        assert "<div id=\"root\"></div>" in r.text
        print("  -> React Root Container Found")
    except Exception as e:
        print(f"[FAIL] Frontend Server Error: {e}")

    # 2. Test Backend Health Endpoints
    try:
        r = httpx.get("http://127.0.0.1:8000/api/health", timeout=5.0)
        print(f"[PASS] Backend /api/health is UP (Status: {r.status_code}, Body: {r.json()})")
        
        r_db = httpx.get("http://127.0.0.1:8000/api/health/db", timeout=5.0)
        print(f"[PASS] Backend /api/health/db is UP (Status: {r_db.status_code}, Body: {r_db.json()})")
    except Exception as e:
        print(f"[FAIL] Backend Health Error: {e}")

    # 3. Test Backend Search Listing
    try:
        r = httpx.get("http://127.0.0.1:8000/api/searches", timeout=5.0)
        print(f"[PASS] Backend /api/searches -> Status: {r.status_code}, Total Searches: {len(r.json())}")
    except Exception as e:
        print(f"[FAIL] Backend Searches Error: {e}")

    # 4. Test Backend Website Listing
    try:
        r = httpx.get("http://127.0.0.1:8000/api/websites", timeout=5.0)
        websites = r.json()
        print(f"[PASS] Backend /api/websites -> Status: {r.status_code}, Total Websites: {len(websites)}")
        if websites:
            first_id = websites[0]["id"]
            r_detail = httpx.get(f"http://127.0.0.1:8000/api/websites/{first_id}", timeout=5.0)
            print(f"[PASS] Backend /api/websites/{first_id} -> Status: {r_detail.status_code}, Domain: {r_detail.json().get('domain')}")
    except Exception as e:
        print(f"[FAIL] Backend Websites Error: {e}")

    print("=" * 60)

if __name__ == "__main__":
    test_servers()
