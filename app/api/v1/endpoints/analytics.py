import httpx
from fastapi import APIRouter, Depends, Request, Response, status, HTTPException
from typing import Dict, Any

from app.api import deps
from app.core.config import settings
from app.schemas.analytics import AnalyticsEventCreate

router = APIRouter()

ANALYTICS_SERVICE_URL = "http://localhost:8010"


@router.post("/track", status_code=status.HTTP_202_ACCEPTED)
async def track_analytics_event(
    request: Request,
    payload: AnalyticsEventCreate,
):
    headers = {"user-agent": request.headers.get("user-agent", "")}
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        headers["x-forwarded-for"] = forwarded
        
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{ANALYTICS_SERVICE_URL}/analytics/track",
                json=payload.model_dump(),
                headers=headers,
                timeout=5.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail="Analytics service unavailable")


@router.get("/summary")
async def get_analytics_summary(
    request: Request,
    current_user=Depends(deps.check_permission("view_performance_metrics")),
    days: int = 30,
) -> Dict[str, Any]:
    # We must pass the authorization header since the analytics service expects it
    auth_header = request.headers.get("authorization")
    headers = {}
    if auth_header:
        headers["authorization"] = auth_header

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{ANALYTICS_SERVICE_URL}/analytics/summary",
                params={"days": days},
                headers=headers,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail="Analytics service unavailable")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail="Analytics service error")

