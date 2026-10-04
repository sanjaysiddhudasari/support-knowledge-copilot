"""Signup endpoint tests. Supabase is replaced with fakes, so no real
credentials or network calls are needed.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth as auth_api  # noqa: E402
from app.main import app  # noqa: E402


VALID = {
    "email": "newuser@example.com",
    "password": "Str0ngPassword!",
    "confirm_password": "Str0ngPassword!",
}


class FakeAuth:
    def __init__(self):
        self.sign_up_calls = []
        self.sign_in_calls = []
        self.raise_error = None
        self.return_session = True

    def sign_up(self, payload):
        self.sign_up_calls.append(dict(payload))

        if self.raise_error:
            raise RuntimeError(self.raise_error)

        session = (
            SimpleNamespace(
                access_token="access",
                refresh_token="refresh",
                expires_in=3600,
            )
            if self.return_session
            else None
        )

        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            session=session,
        )

    def sign_in_with_password(self, payload):
        self.sign_in_calls.append(dict(payload))

        return SimpleNamespace(
            session=SimpleNamespace(
                access_token="access",
                refresh_token="refresh",
                expires_in=3600,
            )
        )


class FakeTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def upsert(self, values):
        self.store.append((self.name, dict(values)))
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class FakeAdmin:
    def __init__(self):
        self.store = []

    def table(self, name):
        return FakeTable(self.store, name)

    def profile_writes(self):
        return [
            values
            for name, values in self.store
            if name == "profiles"
        ]


@pytest.fixture
def env(monkeypatch):
    fake_auth = FakeAuth()
    fake_admin = FakeAdmin()

    monkeypatch.setattr(auth_api, "supabase", SimpleNamespace(auth=fake_auth))
    monkeypatch.setattr(auth_api, "supabase_admin", fake_admin)

    with TestClient(app) as client:
        yield client, fake_auth, fake_admin


def signup(client, **overrides):
    payload = dict(VALID)
    payload.update(overrides)
    return client.post("/api/auth/signup", json=payload)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_signup_success_returns_session(env):
    client, fake_auth, fake_admin = env

    response = signup(client)

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "success"
    assert body["access_token"] == "access"
    assert fake_auth.sign_up_calls[0]["email"] == VALID["email"]


def test_new_user_profile_is_public_not_admin(env):
    client, _, fake_admin = env

    signup(client)

    writes = fake_admin.profile_writes()

    assert len(writes) == 1
    assert writes[0]["id"] == "user-1"
    assert writes[0]["email"] == VALID["email"]
    assert writes[0]["access_level"] == "public"
    assert writes[0]["access_level"] != "admin"


def test_signup_requires_email(env):
    client, fake_auth, _ = env

    response = signup(client, email="   ")

    assert response.status_code == 400
    assert fake_auth.sign_up_calls == []


def test_signup_rejects_invalid_email(env):
    client, fake_auth, _ = env

    response = signup(client, email="not-an-email")

    assert response.status_code == 400
    assert "valid email" in response.json()["detail"].lower()
    assert fake_auth.sign_up_calls == []


def test_signup_rejects_short_password(env):
    client, fake_auth, _ = env

    response = signup(client, password="short", confirm_password="short")

    assert response.status_code == 400
    assert "at least" in response.json()["detail"].lower()
    assert fake_auth.sign_up_calls == []


def test_signup_rejects_password_mismatch(env):
    client, fake_auth, _ = env

    response = signup(client, confirm_password="DifferentPassword1!")

    assert response.status_code == 400
    assert "do not match" in response.json()["detail"].lower()
    assert fake_auth.sign_up_calls == []


def test_signup_surfaces_supabase_error(env):
    client, fake_auth, fake_admin = env
    fake_auth.raise_error = "User already registered"

    response = signup(client)

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]
    assert fake_admin.profile_writes() == []


def test_signup_handles_email_confirmation_flow(env):
    client, fake_auth, fake_admin = env
    fake_auth.return_session = False

    response = signup(client)

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "confirmation_required"
    assert "access_token" not in body
    # the profile is still provisioned for the created user
    assert fake_admin.profile_writes()[0]["access_level"] == "public"


# ---------------------------------------------------------------------------
# Existing login must keep working
# ---------------------------------------------------------------------------


def test_login_still_works(env):
    client, fake_auth, _ = env

    response = client.post(
        "/api/auth/login",
        json={"email": VALID["email"], "password": VALID["password"]},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "access"
    assert fake_auth.sign_in_calls[0]["email"] == VALID["email"]


def test_login_failure_is_401(monkeypatch):
    class Broken:
        def sign_in_with_password(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        auth_api, "supabase", SimpleNamespace(auth=Broken())
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "a@b.c", "password": "whatever"},
        )

    assert response.status_code == 401
