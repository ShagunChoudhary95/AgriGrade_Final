import asyncio
import os
from typing import Any

import httpx

from app.core.config import settings

MARKET_API_URL = (
    "https://api.data.gov.in/resource/"
    "9ef84268-d588-465a-a308-a864a43d0070"
)

# Standard browser headers to prevent WAF connection drops and TCP resets
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Crop name mappings from AgriGrade classifier / common labels to official AGMARKNET commodity names
CROP_NAME_MAPPINGS: dict[str, str] = {
    "corn (maize)": "Maize",
    "corn": "Maize",
    "maize": "Maize",
    "pepper, bell": "Capsicum",
    "pepper bell": "Capsicum",
    "bell pepper": "Capsicum",
    "capsicum": "Capsicum",
    "cherry (including sour)": "Cherry",
    "grape": "Grapes",
    "grapes": "Grapes",
    "soybean": "Soyabean",
    "soyabean": "Soyabean",
    "squash": "Squash(Pumpkin)",
    "potato": "Potato",
    "tomato": "Tomato",
    "apple": "Apple",
    "orange": "Orange",
    "peach": "Peach",
    "strawberry": "Strawberry",
}


def _parse_price(val: Any) -> float | None:
    """Safely parse price values into float or None without throwing."""
    if val is None:
        return None
    try:
        cleaned = str(val).replace(",", "").strip()
        if not cleaned or cleaned.upper() in ("NA", "N/A", "NULL", "NONE"):
            return None
        num = float(cleaned)
        return num if num >= 0 else None
    except (ValueError, TypeError):
        return None


class MarketService:
    def __init__(self) -> None:
        self.api_url = (
            getattr(settings, "market_api_base_url", "")
            or MARKET_API_URL
        )

    def _get_api_key(self) -> str:
        """Retrieve API key with fallback across settings and environment."""
        if hasattr(settings, "effective_market_api_key") and settings.effective_market_api_key:
            return settings.effective_market_api_key
        return (
            getattr(settings, "market_api_key", "")
            or os.getenv("DATA_GOV_API_KEY", "")
            or os.getenv("MARKET_API_KEY", "")
        ).strip()

    def normalize_commodity(self, crop: str) -> str:
        """Map model/input crop names to official AGMARKNET commodity names."""
        clean = crop.strip()
        lower = clean.lower()
        if lower in CROP_NAME_MAPPINGS:
            return CROP_NAME_MAPPINGS[lower]
        return clean.title() if clean else ""

    async def get_market_prices(
        self,
        crop: str,
        state: str = "",
        district: str = "",
        market: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Fetch daily mandi prices from India's official AGMARKNET API on data.gov.in."""

        crop = crop.strip()
        state = state.strip()
        district = district.strip()
        market = market.strip()

        if not crop:
            raise ValueError("Crop name is required.")

        if not 1 <= limit <= 1000:
            raise ValueError("Limit must be between 1 and 1000.")

        api_key = self._get_api_key()

        if not api_key:
            return {
                "success": False,
                "available": False,
                "message": "Government market API key is not configured.",
                "crop": crop,
                "total_records": 0,
                "prices": [],
            }

        commodity_query = self.normalize_commodity(crop)

        params: dict[str, Any] = {
            "api-key": api_key,
            "format": "json",
            "limit": limit,
            "offset": offset,
            "filters[commodity]": commodity_query,
        }

        if state:
            params["filters[state]"] = state
        if district:
            params["filters[district]"] = district
        if market:
            params["filters[market]"] = market

        timeout = httpx.Timeout(25.0, connect=10.0)
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    follow_redirects=True,
                    headers=REQUEST_HEADERS,
                ) as client:
                    response = await client.get(
                        self.api_url,
                        params=params,
                    )

                if response.status_code in (401, 403):
                    return {
                        "success": False,
                        "available": False,
                        "message": "Government market API key is invalid or unauthorized.",
                        "crop": crop,
                        "total_records": 0,
                        "prices": [],
                    }

                if response.status_code == 429:
                    return {
                        "success": False,
                        "available": False,
                        "message": "Government market API rate limit exceeded. Please try again later.",
                        "crop": crop,
                        "total_records": 0,
                        "prices": [],
                    }

                if response.status_code in (500, 502, 503, 504):
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    return {
                        "success": False,
                        "available": False,
                        "message": "Government market API returned an HTTP error.",
                        "crop": crop,
                        "total_records": 0,
                        "prices": [],
                    }

                response.raise_for_status()

                try:
                    data = response.json()
                except ValueError:
                    return {
                        "success": False,
                        "available": False,
                        "message": "Market API returned invalid JSON.",
                        "crop": crop,
                        "total_records": 0,
                        "prices": [],
                    }

                records = data.get("records", [])

                prices = [
                    {
                        "state": item.get("state") or "",
                        "district": item.get("district") or "",
                        "market": item.get("market") or "",
                        "commodity": item.get("commodity") or commodity_query,
                        "variety": item.get("variety") or "",
                        "grade": item.get("grade") or "",
                        "arrival_date": item.get("arrival_date") or "",
                        "min_price": _parse_price(item.get("min_price")),
                        "max_price": _parse_price(item.get("max_price")),
                        "modal_price": _parse_price(item.get("modal_price")),
                    }
                    for item in records
                ]

                total_count = data.get("total", len(records))

                return {
                    "success": True,
                    "available": True,
                    "crop": crop,
                    "commodity": commodity_query,
                    "state": state or None,
                    "district": district or None,
                    "market": market or None,
                    "total_records": total_count,
                    "total": total_count,
                    "count": len(prices),
                    "offset": offset,
                    "limit": limit,
                    "prices": prices,
                    "records": prices,
                    "currency": "INR",
                    "price_unit": "₹/quintal",
                    "unit": "₹/quintal",
                    "source": "AGMARKNET / data.gov.in",
                }

            except httpx.TimeoutException:
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "available": False,
                    "message": "Market API request timed out.",
                    "crop": crop,
                    "total_records": 0,
                    "prices": [],
                }

            except httpx.HTTPStatusError:
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "available": False,
                    "message": "Government market API returned an HTTP error.",
                    "crop": crop,
                    "total_records": 0,
                    "prices": [],
                }

            except httpx.RequestError:
                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                return {
                    "success": False,
                    "available": False,
                    "message": "Unable to connect to the market API.",
                    "crop": crop,
                    "total_records": 0,
                    "prices": [],
                }

        return {
            "success": False,
            "available": False,
            "message": "Market prices could not be loaded.",
            "crop": crop,
            "total_records": 0,
            "prices": [],
        }


market_service = MarketService()
