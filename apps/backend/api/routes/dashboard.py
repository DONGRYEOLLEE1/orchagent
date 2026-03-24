from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from schemas.dashboard import (
    DashboardDailyUsagePointResponse,
    DashboardDailyUsageResponse,
    DashboardLiveTraceRowResponse,
    DashboardLiveTracesResponse,
    DashboardSummaryResponse,
)
from services.dashboard_service import DashboardService
from services.security_service import get_current_user

router = APIRouter()


def _resolve_target_user_id(current_user, requested_user_id: str | None) -> str:
    if requested_user_id is None or requested_user_id == current_user.id:
        return current_user.id
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return requested_user_id


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    user_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    target_user_id = _resolve_target_user_id(current_user, user_id)
    summary = await DashboardService.get_summary(
        db,
        user_id=target_user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return DashboardSummaryResponse.model_validate(summary, from_attributes=True)


@router.get("/dashboard/daily-usage", response_model=DashboardDailyUsageResponse)
async def get_dashboard_daily_usage(
    user_id: str | None = Query(None),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    target_user_id = _resolve_target_user_id(current_user, user_id)
    points = await DashboardService.get_daily_usage_series(
        db,
        user_id=target_user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return DashboardDailyUsageResponse(
        user_id=target_user_id,
        points=[
            DashboardDailyUsagePointResponse.model_validate(point, from_attributes=True)
            for point in points
        ],
    )


@router.get("/dashboard/live-traces", response_model=DashboardLiveTracesResponse)
async def get_dashboard_live_traces(
    user_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    target_user_id = _resolve_target_user_id(current_user, user_id)
    rows = await DashboardService.get_live_traces(
        db,
        user_id=target_user_id,
        limit=limit,
    )
    return DashboardLiveTracesResponse(
        user_id=target_user_id,
        rows=[
            DashboardLiveTraceRowResponse.model_validate(row, from_attributes=True)
            for row in rows
        ],
    )
