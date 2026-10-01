from pydantic import BaseModel


class User(BaseModel):
    id: str
    email: str
    access_level: str


class LoginRequest(BaseModel):
    email: str
    password: str