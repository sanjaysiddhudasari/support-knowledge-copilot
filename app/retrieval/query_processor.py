"""Query preprocessing pipeline for enhanced hybrid retrieval recall.

Normalizes user queries, expands technical abbreviations (e.g. SSO, MFA, ACL),
and extracts key search terms to boost lexical and dense retrieval accuracy.
"""

import re
from dataclasses import dataclass


COMMON_ABBREVIATIONS: dict[str, str] = {
    "sso": "Single Sign-On (SSO)",
    "mfa": "Multi-Factor Authentication (MFA)",
    "2fa": "Two-Factor Authentication (2FA)",
    "acl": "Access Control List (ACL)",
    "rbac": "Role-Based Access Control (RBAC)",
    "iam": "Identity and Access Management (IAM)",
    "sla": "Service Level Agreement (SLA)",
    "api": "Application Programming Interface (API)",
    "sdk": "Software Development Kit (SDK)",
    "kb": "Knowledge Base (KB)",
    "db": "Database (DB)",
    "tls": "Transport Layer Security (TLS)",
    "ssl": "Secure Sockets Layer (SSL)",
    "vm": "Virtual Machine (VM)",
    "os": "Operating System (OS)",
}


@dataclass
class ProcessedQuery:
    original: str
    normalized: str
    expanded: str
    keywords: list[str]


class QueryProcessor:
    """Processes user queries before dispatching to dense and BM25 retrievers."""

    def __init__(
        self,
        abbreviations: dict[str, str] | None = None,
    ):
        self.abbreviations = abbreviations or COMMON_ABBREVIATIONS

    def normalize(self, query: str) -> str:
        """Strip redundant whitespace, normalize casing and punctuation spacing."""
        text = re.sub(r"\s+", " ", query or "").strip()
        return text

    def expand_abbreviations(self, query: str) -> str:
        """Expand recognized technical acronyms if they appear as standalone words."""
        words = re.findall(r"\b[\w-]+\b", query)
        expanded = query

        for word in words:
            lower = word.lower()
            if lower in self.abbreviations:
                expansion = self.abbreviations[lower]
                # Avoid expanding if already expanded in query
                if expansion.lower() not in query.lower():
                    # Replace whole-word occurrences only
                    pattern = rf"\b{re.escape(word)}\b"
                    expanded = re.sub(pattern, expansion, expanded, flags=re.IGNORECASE)

        return expanded

    def extract_keywords(self, query: str) -> list[str]:
        """Extract alphanumeric tokens (excluding common punctuation)."""
        tokens = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", query.lower())
        return tokens

    def process(self, raw_query: str) -> ProcessedQuery:
        """Execute the full query preprocessing pipeline."""
        normalized = self.normalize(raw_query)
        expanded = self.expand_abbreviations(normalized)
        keywords = self.extract_keywords(expanded)

        return ProcessedQuery(
            original=raw_query,
            normalized=normalized,
            expanded=expanded,
            keywords=keywords,
        )
