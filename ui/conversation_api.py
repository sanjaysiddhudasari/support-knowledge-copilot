"""HTTP client for the persistent conversation endpoints.

Kept separate from ``app.py`` so the Streamlit script stays readable and this
layer is testable on its own. Every method is failure-tolerant: a storage
problem returns ``None``/``[]`` instead of raising, so the chat UI degrades to
a working (if non-persistent) session rather than crashing.
"""

from __future__ import annotations

import requests


class ConversationAPI:
    """Thin wrapper over ``/api/conversations`` for an authenticated user."""

    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token
        self.timeout = timeout

    # -- plumbing ---------------------------------------------------------

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _url(self, path: str = "") -> str:
        return f"{self.base_url}/api/conversations{path}"

    # -- endpoints --------------------------------------------------------

    def create(self, title: str | None = None) -> dict | None:
        try:
            response = requests.post(
                self._url(),
                json={"title": title} if title else {},
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def list(self) -> list[dict]:
        try:
            response = requests.get(
                self._url(),
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return []

        return data if isinstance(data, list) else []

    def messages(self, conversation_id: str) -> list[dict]:
        try:
            response = requests.get(
                self._url(f"/{conversation_id}/messages"),
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return []

        return data if isinstance(data, list) else []

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        query_id: str | None = None,
        confidence: float | None = None,
        answerable: bool | None = None,
        citations: list[dict] | None = None,
    ) -> dict | None:
        """Persist one turn. ``None`` means the write did not land."""

        payload = {
            "role": role,
            "content": content,
            "query_id": query_id,
            "confidence": confidence,
            "answerable": answerable,
            "citations": citations,
        }

        try:
            response = requests.post(
                self._url(f"/{conversation_id}/messages"),
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def rename(self, conversation_id: str, title: str) -> dict | None:
        try:
            response = requests.patch(
                self._url(f"/{conversation_id}"),
                json={"title": title},
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            return None

    def delete(self, conversation_id: str) -> bool:
        try:
            response = requests.delete(
                self._url(f"/{conversation_id}"),
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except (requests.RequestException, ValueError):
            return False

        return True
