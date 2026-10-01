from fastapi import APIRouter, HTTPException

from app.auth.client import supabase
from app.auth.models import LoginRequest

router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


@router.post("/login")
def login(request: LoginRequest):
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    if not response.session:
        raise HTTPException(
            status_code=401,
            detail="Login failed",
        )

    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "expires_in": response.session.expires_in,
    }