import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Mock ML libraries and inference if not installed in the lightweight test environment
for mod in [
    "torch", "torch.nn", "torch.nn.functional", "torchvision",
    "torchvision.transforms", "PIL", "PIL.Image", "app.services.inference"
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.market import (
    MarketService,
    _parse_price,
    CROP_NAME_MAPPINGS,
)
from main import app


def test_parse_price_utility():
    assert _parse_price("1,450.00") == 1450.0
    assert _parse_price("2500") == 2500.0
    assert _parse_price(1800) == 1800.0
    assert _parse_price(1800.75) == 1800.75
    assert _parse_price(None) is None
    assert _parse_price("") is None
    assert _parse_price("NA") is None
    assert _parse_price("N/A") is None
    assert _parse_price("null") is None
    assert _parse_price("invalid") is None


def test_commodity_normalization():
    service = MarketService()
    assert service.normalize_commodity("Corn (maize)") == "Maize"
    assert service.normalize_commodity("corn") == "Maize"
    assert service.normalize_commodity("Pepper, bell") == "Capsicum"
    assert service.normalize_commodity("grape") == "Grapes"
    assert service.normalize_commodity("tomato") == "Tomato"
    assert service.normalize_commodity("Potato") == "Potato"
    assert service.normalize_commodity("wheat") == "Wheat"


async def test_missing_api_key_returns_graceful_unavailable_state():
    service = MarketService()
    with patch.object(service, "_get_api_key", return_value=""):
        result = await service.get_market_prices(crop="Tomato")
        assert result["success"] is False
        assert result["available"] is False
        assert "not configured" in result["message"]
        assert result["prices"] == []
        assert result["total_records"] == 0


async def test_data_mapping_matches_expected_schema():
    service = MarketService()
    mock_api_response = {
        "index_name": "9ef84268-d588-465a-a308-a864a43d0070",
        "title": "Current Daily Price of Various Commodities from Various Markets (Mandi)",
        "total": 1,
        "count": 1,
        "records": [
            {
                "state": "Uttar Pradesh",
                "district": "Agra",
                "market": "Achnera",
                "commodity": "Potato",
                "variety": "Desi",
                "grade": "FAQ",
                "arrival_date": "24/10/2026",
                "min_price": "1400",
                "max_price": "1550",
                "modal_price": "1480",
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_api_response
    mock_resp.raise_for_status = MagicMock()

    with patch.object(service, "_get_api_key", return_value="dummy_test_key"), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        result = await service.get_market_prices(crop="Potato", state="Uttar Pradesh")

        assert result["success"] is True
        assert result["available"] is True
        assert result["currency"] == "INR"
        assert result["price_unit"] == "₹/quintal"
        assert result["total_records"] == 1
        assert len(result["prices"]) == 1

        price_entry = result["prices"][0]
        assert price_entry["state"] == "Uttar Pradesh"
        assert price_entry["district"] == "Agra"
        assert price_entry["market"] == "Achnera"
        assert price_entry["commodity"] == "Potato"
        assert price_entry["variety"] == "Desi"
        assert price_entry["grade"] == "FAQ"
        assert price_entry["arrival_date"] == "24/10/2026"
        assert price_entry["min_price"] == 1400.0
        assert price_entry["max_price"] == 1550.0
        assert price_entry["modal_price"] == 1480.0


async def test_graceful_handling_of_http_errors():
    import httpx
    service = MarketService()

    # Test 401/403
    mock_resp_403 = MagicMock()
    mock_resp_403.status_code = 403
    with patch.object(service, "_get_api_key", return_value="dummy_key"), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp_403):
        res = await service.get_market_prices(crop="Tomato")
        assert res["available"] is False
        assert "invalid or unauthorized" in res["message"]

    # Test 502 Bad Gateway
    mock_resp_502 = MagicMock()
    mock_resp_502.status_code = 502
    with patch.object(service, "_get_api_key", return_value="dummy_key"), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp_502), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        res = await service.get_market_prices(crop="Tomato")
        assert res["available"] is False
        assert "HTTP error" in res["message"]

    # Test TimeoutException
    with patch.object(service, "_get_api_key", return_value="dummy_key"), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Timeout")), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        res = await service.get_market_prices(crop="Tomato")
        assert res["available"] is False
        assert "timed out" in res["message"]


def test_fastapi_endpoints_integration():
    client = TestClient(app)

    # 1. Health endpoint still functional
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    # 2. Market endpoint validation
    # Crop missing -> 422 or 400
    missing_crop = client.get("/api/market-prices")
    assert missing_crop.status_code in (400, 422)

    # 3. Market endpoint called with valid param
    with patch("app.api.routes.market_service.get_market_prices", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "success": True,
            "available": True,
            "crop": "Tomato",
            "commodity": "Tomato",
            "prices": [
                {
                    "state": "Maharashtra",
                    "district": "Pune",
                    "market": "Pune",
                    "commodity": "Tomato",
                    "variety": "Local",
                    "grade": "FAQ",
                    "arrival_date": "24/10/2026",
                    "min_price": 1200.0,
                    "max_price": 1600.0,
                    "modal_price": 1400.0,
                }
            ],
            "total_records": 1,
            "price_unit": "₹/quintal",
        }
        resp = client.get("/api/market-prices?crop=Tomato&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["available"] is True
        assert len(data["prices"]) == 1
        assert data["prices"][0]["modal_price"] == 1400.0

    # 4. Secondary market route /api/market/prices
    with patch("app.api.market.market_service.get_market_prices", new_callable=AsyncMock) as mock_get_market:
        mock_get_market.return_value = {
            "success": True,
            "available": True,
            "crop": "Tomato",
            "commodity": "Tomato",
            "prices": [],
            "records": [],
            "total_records": 0,
            "price_unit": "₹/quintal",
        }
        resp2 = client.get("/api/market/prices?commodity=Tomato&limit=5")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert data2["available"] is True


if __name__ == "__main__":
    test_parse_price_utility()
    test_commodity_normalization()
    asyncio.run(test_missing_api_key_returns_graceful_unavailable_state())
    asyncio.run(test_data_mapping_matches_expected_schema())
    asyncio.run(test_graceful_handling_of_http_errors())
    test_fastapi_endpoints_integration()
    print("ALL MARKET PRICE TESTS PASSED!")
