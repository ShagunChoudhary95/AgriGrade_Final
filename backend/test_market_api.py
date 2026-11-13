import os
import httpx
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("MARKET_API_KEY") or os.getenv("DATA_GOV_API_KEY")

if not key:
    print("MARKET_API_KEY or DATA_GOV_API_KEY is missing from backend .env")
else:
    url = (
        "https://api.data.gov.in/resource/"
        "9ef84268-d588-465a-a308-a864a43d0070"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    try:
        response = httpx.get(
            url,
            params={
                "api-key": key,
                "format": "json",
                "limit": 1,
            },
            headers=headers,
            follow_redirects=True,
            timeout=30,
        )

        print("Status:", response.status_code)
        print("Response:", response.text[:500])

    except httpx.RequestError as exc:
        print("Connection error:", type(exc).__name__)
