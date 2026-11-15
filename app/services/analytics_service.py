"""Analytics service for Support Knowledge Copilot.

Aggregates operational metrics, query volume, answerability rates, average
confidence, user feedback, and knowledge base document coverage from Supabase.
"""

from typing import Any
from collections import Counter
from app.auth.client import supabase_admin


class AnalyticsService:

    def __init__(self, client: Any = None):
        self.client = client if client is not None else supabase_admin

    def get_system_analytics(self) -> dict:
        """Compute system-wide analytics for admin dashboards."""
        # 1. Fetch recent messages
        messages_res = (
            self.client.table("messages")
            .select("id, role, content, confidence, answerable, citations, feedback, feedback_comment, created_at")
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )
        messages: list[dict] = getattr(messages_res, "data", []) or []

        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]

        total_queries = len(user_messages)
        total_answers = len(assistant_messages)

        # Answerability
        answerable_count = sum(1 for m in assistant_messages if m.get("answerable") is True)
        unanswerable_count = sum(1 for m in assistant_messages if m.get("answerable") is False)
        answerability_rate = round(answerable_count / total_answers, 4) if total_answers > 0 else 0.0

        # Confidence
        confidences = [
            float(m["confidence"])
            for m in assistant_messages
            if m.get("confidence") is not None
        ]
        avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0

        # Feedback
        positive_feedback = sum(1 for m in assistant_messages if m.get("feedback") == "positive")
        negative_feedback = sum(1 for m in assistant_messages if m.get("feedback") == "negative")
        total_feedback = positive_feedback + negative_feedback
        satisfaction_rate = (
            round(positive_feedback / total_feedback, 4) if total_feedback > 0 else 1.0
        )

        recent_negative = [
            {
                "message_id": m.get("id"),
                "answer_preview": (m.get("content") or "")[:120] + "...",
                "comment": m.get("feedback_comment"),
                "created_at": m.get("created_at"),
            }
            for m in assistant_messages
            if m.get("feedback") == "negative"
        ][:5]

        # Top cited sources
        source_counter = Counter()
        for m in assistant_messages:
            cits = m.get("citations") or []
            if isinstance(cits, list):
                for c in cits:
                    if isinstance(c, dict):
                        src = c.get("source") or c.get("chunk_id", "").split("_chunk_")[0]
                        if src:
                            source_counter[src] += 1

        top_sources = [
            {"source": src, "citations_count": count}
            for src, count in source_counter.most_common(5)
        ]

        # 2. Fetch document statistics
        docs_res = (
            self.client.table("documents")
            .select("id, file_type, status, size_bytes")
            .execute()
        )
        docs: list[dict] = getattr(docs_res, "data", []) or []

        type_counter = Counter(d.get("file_type") or "unknown" for d in docs)
        status_counter = Counter(d.get("status") or "unknown" for d in docs)
        total_kb_bytes = sum(int(d.get("size_bytes") or 0) for d in docs)

        return {
            "queries": {
                "total_queries": total_queries,
                "total_answers": total_answers,
                "answerable_count": answerable_count,
                "unanswerable_count": unanswerable_count,
                "answerability_rate": answerability_rate,
                "average_confidence": avg_confidence,
            },
            "feedback": {
                "positive": positive_feedback,
                "negative": negative_feedback,
                "total_feedback": total_feedback,
                "satisfaction_rate": satisfaction_rate,
                "recent_negative_feedback": recent_negative,
            },
            "sources": {
                "top_cited": top_sources,
            },
            "documents": {
                "total_count": len(docs),
                "total_size_kb": total_kb_bytes // 1024,
                "by_file_type": dict(type_counter),
                "by_status": dict(status_counter),
            },
        }
