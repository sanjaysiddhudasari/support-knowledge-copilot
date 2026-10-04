from pydantic import BaseModel


class User(BaseModel):
    id: str
    email: str
    access_level: str


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str
    # Optional: validated when the client sends it (the UI collects it).
    confirm_password: str | None = None
