"""HTTP routes for the analytics module."""

from datetime import date

from fastapi import APIRouter, HTTPException

from rec_console.module.analytics.client import AnalyticsClient, AnalyticsError

router = APIRouter()


@router.get("/api/analytics/business")
def business_analytics(
    date_from: date, date_to: date, scene: str = "", refresh: bool = False
):
    if date_from > date_to:
        raise HTTPException(
            status_code=400, detail="date_from must not be after date_to"
        )
    if (date_to - date_from).days > 366:
        raise HTTPException(
            status_code=400, detail="date range must not exceed 366 days"
        )
    try:
        return AnalyticsClient().query(
            date_from.isoformat(), date_to.isoformat(), scene.strip(), refresh
        )
    except AnalyticsError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
