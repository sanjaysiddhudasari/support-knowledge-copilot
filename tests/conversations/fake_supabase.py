"""In-memory stand-in for the ``supabase-py`` table API.

Only the chain the conversation service actually uses is implemented:
``table(name).select/insert/update/delete().eq().order().execute()``.
It is deliberately small so persistence tests need no network or credentials.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, store: "FakeSupabase", name: str):
        self.store = store
        self.name = name
        self._action = None
        self._payload = None
        self._filters: list[tuple[str, object]] = []
        self._order = None
        self._desc = False
        self._limit = None

    # -- builders ---------------------------------------------------------

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

    # -- execution --------------------------------------------------------

    def _matches(self, row: dict) -> bool:
        return all(row.get(k) == v for k, v in self._filters)

    def _matching(self) -> list[dict]:
        return [row for row in self.store.rows(self.name) if self._matches(row)]

    def _sorted(self, rows: list[dict]) -> list[dict]:
        if self._order is None:
            return rows

        # Sequence is a stable tiebreaker so same-timestamp inserts keep
        # insertion order, mirroring `order by created_at` with a row id.
        return sorted(
            rows,
            key=lambda row: (row.get(self._order), row.get("_seq", 0)),
            reverse=self._desc,
        )

    def execute(self) -> FakeResponse:
        if self._action == "insert":
            inserted = []

            for item in self._payload:
                row = dict(item)
                row.setdefault("id", str(uuid.uuid4()))

                # The database owns timestamps: defaults now() on insert,
                # trigger now() on update. Client values are ignored.
                if "created_at" in self.store.FIELDS.get(self.name, ()):
                    row["created_at"] = self.store.next_timestamp()

                if "updated_at" in self.store.FIELDS.get(self.name, ()):
                    row["updated_at"] = row.get(
                        "created_at"
                    ) or self.store.next_timestamp()

                self.store.add(self.name, row)
                inserted.append(self.store.clean(self.name, row))

            return FakeResponse(inserted)

        if self._action == "update":
            updated = []

            for row in self._matching():
                row.update(self._payload)

                # Emulate the `before update` trigger that owns updated_at.
                if "updated_at" in self.store.FIELDS.get(self.name, ()):
                    row["updated_at"] = self.store.next_timestamp()

                updated.append(self.store.clean(self.name, row))

            return FakeResponse(updated)

        if self._action == "delete":
            doomed = self._matching()

            self.store.remove(self.name, doomed)
            return FakeResponse(
                [self.store.clean(self.name, row) for row in doomed]
            )

        rows = self._sorted(self._matching())

        if self._limit is not None:
            rows = rows[: self._limit]

        return FakeResponse([self.store.clean(self.name, row) for row in rows])


class FakeSupabase:
    """Minimal client exposing ``.table(name)``."""

    FIELDS = {
        "conversations": {
            "id", "user_id", "title", "created_at", "updated_at",
        },
        "messages": {
            "id", "conversation_id", "role", "content", "query_id",
            "confidence", "answerable", "citations", "created_at",
        },
    }

    def __init__(self):
        self._tables: dict[str, list[dict]] = {
            "conversations": [],
            "messages": [],
        }
        self._sequence = 0
        self._clock = 0

    # -- storage ----------------------------------------------------------

    def rows(self, name: str) -> list[dict]:
        return self._tables.setdefault(name, [])

    def add(self, name: str, row: dict) -> None:
        self._sequence += 1
        row["_seq"] = self._sequence
        self.rows(name).append(row)

    def remove(self, name: str, doomed: list[dict]) -> None:
        for row in doomed:
            self.rows(name).remove(row)

            # Emulate `on delete cascade` from conversations -> messages.
            if name == "conversations":
                self._tables["messages"] = [
                    message
                    for message in self._tables.get("messages", [])
                    if message.get("conversation_id") != row.get("id")
                ]

    def clean(self, name: str, row: dict) -> dict:
        """Drop internal bookkeeping and unknown columns, like PostgREST."""

        allowed = self.FIELDS.get(name)

        if allowed is None:
            return {k: v for k, v in row.items() if not k.startswith("_")}

        return {
            key: value
            for key, value in row.items()
            if key in allowed
        }

    def next_timestamp(self) -> str:
        self._clock += 1

        return (
            _BASE_TIME + timedelta(seconds=self._clock)
        ).isoformat()

    # -- supabase-py surface ----------------------------------------------

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def make_client() -> SimpleNamespace:
    """Convenience wrapper kept for symmetry with the real client module."""

    return SimpleNamespace(table=FakeSupabase().table)
