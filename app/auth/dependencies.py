from typing import Any, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.client import supabase, supabase_admin
from app.auth.models import User


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:

    token = credentials.credentials

    try:
        response = supabase.auth.get_user(token)

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    if not response or not response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    auth_user = response.user

    profile_response = (
        supabase_admin
        .table("profiles")
        .select("id, email, access_level")
        .eq("id", auth_user.id)
        .single()
        .execute()
)

    # ponytail: no .single() — 0 rows returns [] not PGRST116 500
    data = profile_response.data
    if isinstance(data, list):
        profile = cast(dict[str, Any] | None, data[0] if data else None)
    else:
        profile = cast(dict[str, Any] | None, data)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User profile not found",
        )

    return User(
        id=profile["id"],
        email=profile["email"],
        access_level=str(profile["access_level"]),
    )