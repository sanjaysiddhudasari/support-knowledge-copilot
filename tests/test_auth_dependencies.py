"""get_current_user: a missing profile is a 403, not a 500.

Regression for the .single() bug: with `.single()`, zero rows raised PGRST116
(500). Without it, [] is handled and yields the intended 403.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.auth import dependencies as deps  # noqa: E402


class FakeAuth:
    def get_user(self, token):
        return SimpleNamespace(user=SimpleNamespace(id="user-1"))


class EmptyProfiles:
    def table(self, name):
        return self

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


def test_missing_profile_returns_403_not_500(monkeypatch):
    monkeypatch.setattr(deps, "supabase", SimpleNamespace(auth=FakeAuth()))
    monkeypatch.setattr(deps, "supabase_admin", EmptyProfiles())

    with pytest.raises(HTTPException) as exc:
        deps.get_current_user(
            SimpleNamespace(credentials="token")
        )

    assert exc.value.status_code == 403


def test_existing_profile_returns_user(monkeypatch):
    class Profiles:
        def __init__(self):
            self.res = None

        def table(self, name):
            return self

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return SimpleNamespace(
                data=[{"id": "user-1", "email": "a@b.c", "access_level": "admin"}]
            )

    monkeypatch.setattr(deps, "supabase", SimpleNamespace(auth=FakeAuth()))
    monkeypatch.setattr(deps, "supabase_admin", Profiles())

    user = deps.get_current_user(SimpleNamespace(credentials="token"))

    assert user.id == "user-1"
    assert user.access_level == "admin"