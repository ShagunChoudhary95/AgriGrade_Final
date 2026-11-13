from fastapi import APIRouter, HTTPException, Query
from app.services.market import market_service

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("/prices")
async def get_market_prices(
    commodity: str | None = None,
    crop: str | None = None,
    state: str | None = None,
    district: str | None = None,
    market: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    target_crop = (commodity or crop or "").strip()
    if not target_crop:
        raise HTTPException(
            status_code=400,
            detail="Commodity or crop query parameter is required.",
        )

    try:
        return await market_service.get_market_prices(
            crop=target_crop,
            state=state or "",
            district=district or "",
            market=market or "",
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
