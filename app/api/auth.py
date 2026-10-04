import re

from fastapi import APIRouter, HTTPException

from app.auth.client import supabase, supabase_admin
from app.auth.models import LoginRequest, SignupRequest

router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)

# New accounts always start at the safest level; never admin.
DEFAULT_ACCESS_LEVEL = "public"

MIN_PASSWORD_LENGTH = 8

# ponytail: shape check only, avoids adding an email-validator dependency
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_signup(request: SignupRequest) -> str:
    """Validate the signup payload and return the cleaned email."""

    email = (request.email or "").strip()

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required.",
        )

    if not _EMAIL_RE.match(email):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address.",
        )

    if len(request.password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=(
                "Password must be at least "
                f"{MIN_PASSWORD_LENGTH} characters."
            ),
        )

    if (
        request.confirm_password is not None
        and request.confirm_password != request.password
    ):
        raise HTTPException(
            status_code=400,
            detail="Passwords do not match.",
        )

    return email


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


@router.post("/signup")
def signup(request: SignupRequest):
    email = _validate_signup(request)

    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": request.password,
        })
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Sign up failed: {error}",
        )

    user = getattr(response, "user", None)

    if user is None:
        raise HTTPException(
            status_code=400,
            detail="Sign up failed: no user was returned.",
        )

    # Idempotent: if a DB trigger already created the profile, this just
    # confirms it. The service-role client is backend-only.
    try:
        supabase_admin.table("profiles").upsert(
            {
                "id": user.id,
                "email": email,
                "access_level": DEFAULT_ACCESS_LEVEL,
            }
        ).execute()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=(
                "Account created but the profile could not be set up. "
                "Contact an administrator."
            ),
        )

    session = getattr(response, "session", None)

    # Supabase may require email confirmation first; do not assume either way.
    if session is None:
        return {
            "status": "confirmation_required",
            "message": (
                "Account created. Check your email to confirm it, "
                "then log in."
            ),
            "email": email,
            "access_level": DEFAULT_ACCESS_LEVEL,
        }

    return {
        "status": "success",
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "expires_in": session.expires_in,
        "email": email,
        "access_level": DEFAULT_ACCESS_LEVEL,
    }
