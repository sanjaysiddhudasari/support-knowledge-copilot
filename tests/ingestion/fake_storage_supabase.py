"""In-memory Supabase fake: table API (documents) + storage API.

Reuses the conversations fake's query-builder shape and adds the minimal
``.storage.from_(bucket).upload/download/remove`` surface the document service
uses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)

DOCUMENT_FIELDS = {
    "id", "user_id", "filename", "storage_path", "file_type",
    "size_bytes", "content_hash", "version", "access_level", "status",
    "created_at", "updated_at",
}


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store: "FakeSupabaseStorage", name: str):
        self.store = store
        self.name = name
        self._action = None
        self._payload = None
        self._filters: list[tuple[str, object]] = []
        self._order = None
        self._desc = False

    def select(self, columns: str = "*"):
        self._action = "select"
        return self

    def insert(self, payload):
        self._action = "insert"
        self._payload = payload if isinstance(payload, list) else [payload]
        return self

    def update(self, payload: dict):
        self._action = "update"
        self._payload = dict(payload)
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, column: str, value):
        self._filters.append((column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self._order = column
        self._desc = desc
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def _matching(self):
        return [
            row
            for row in self.store.rows(self.name)
            if all(row.get(k) == v for k, v in self._filters)
        ]

    def execute(self) -> FakeResponse:
        if self._action == "insert":
            inserted = []

            for item in self._payload:
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))
                self._stamp(row)
                self.store.add(self.name, row)
                inserted.append(self.store.clean(self.name, row))

            return FakeResponse(inserted)

        if self._action == "update":
            updated = []

            for row in self._matching():
                row.update(self._payload)
                self._stamp(row)
                updated.append(self.store.clean(self.name, row))

            return FakeResponse(updated)

        if self._action == "delete":
            doomed = self._matching()
            self.store.remove(self.name, doomed)
            return FakeResponse(
                [self.store.clean(self.name, row) for row in doomed]
            )

        rows = self._matching()

        if self._order:
            rows = sorted(
                rows,
                key=lambda row: row.get(self._order, ""),
                reverse=self._desc,
            )

        if getattr(self, "_limit", None) is not None:
            rows = rows[: self._limit]

        return FakeResponse([self.store.clean(self.name, row) for row in rows])

    def _stamp(self, row: dict) -> None:
        self.store._clock += 1
        moment = _BASE_TIME + timedelta(seconds=self.store._clock)

        row.setdefault("created_at", moment.isoformat())
        row["updated_at"] = moment.isoformat()


class FakeStorageBucket:
    def __init__(self, store: "FakeSupabaseStorage", name: str):
        self.store = store
        self.name = name

    def upload(self, path: str, data: bytes, options=None):
        if path in self.store.blobs:
            raise RuntimeError("The resource already exists")

        self.store.blobs[path] = bytes(data)

    def download(self, path: str) -> bytes:
        if path not in self.store.blobs:
            raise RuntimeError("Object not found")

        return self.store.blobs[path]

    def update(self, path: str, data: bytes):
        # Overwrite semantics: the path must already exist.
        if path not in self.store.blobs:
            raise RuntimeError("Object not found")

        self.store.blobs[path] = bytes(data)

    def remove(self, paths: list[str]):
        for path in paths:
            self.store.blobs.pop(path, None)


class FakeSupabaseStorage:
    """``.table(name)`` + ``.storage.from_(bucket)`` on one in-memory store."""

    FIELDS = {"documents": DOCUMENT_FIELDS}

    def __init__(self):
        self._tables: dict[str, list[dict]] = {"documents": []}
        self.blobs: dict[str, bytes] = {}
        self._clock = 0

    def rows(self, name: str) -> list[dict]:
        return self._tables.setdefault(name, [])

    def add(self, name: str, row: dict) -> None:
        self.rows(name).append(row)

    def remove(self, name: str, doomed: list[dict]) -> None:
        for row in doomed:
            self.rows(name).remove(row)

    def clean(self, name: str, row: dict) -> dict:
        allowed = self.FIELDS.get(name)

        if allowed is None:
            return dict(row)

        return {k: v for k, v in row.items() if k in allowed}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    @property
    def storage(self) -> "FakeSupabaseStorage":
        return self

    def from_(self, bucket: str) -> FakeStorageBucket:
        return FakeStorageBucket(self, bucket)