"""Analytics API routes for Support Knowledge Copilot (Admin only)."""

from fastapi import APIRouter, Depends, HTTPException, status
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/api/admin/analytics",
    tags=["Analytics"],
)

_analytics_service: AnalyticsService | None = None


def get_analytics_service() -> AnalyticsService:
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


@router.get("")
def get_analytics(
    current_user: User = Depends(get_current_user),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Retrieve system-wide analytics, quality metrics, and document stats."""
    if current_user.access_level != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    try:
        return service.get_system_analytics()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate analytics: {error}",
        )
