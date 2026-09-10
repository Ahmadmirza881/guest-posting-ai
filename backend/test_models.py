import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY", "")

async def test():
    async with httpx.AsyncClient() as client:
        # Check models list
        r = await client.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}")
        print("Status:", r.status_code)
        if r.status_code == 200:
            models = [m['name'] for m in r.json().get('models', []) if 'generateContent' in m.get('supportedGenerationMethods', [])]
            print("Available models:", models[:5])
        else:
            print("Error:", r.text)

asyncio.run(test())
