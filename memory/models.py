"""Small, dependency-free models used by the memory subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


MEMORY_TYPES = {
    "fact",
    "preference",
    "relationship",
    "event",
    "opinion",
    "interest",
}

MEMORY_CATEGORIES = (
    "facts",
    "preferences",
    "relationships",
    "events",
    "interests",
    "opinions",
)

TYPE_TO_CATEGORY = {
    "fact": "facts",
    "preference": "preferences",
    "relationship": "relationships",
    "event": "events",
    "opinion": "opinions",
    "interest": "interests",
}


def now_iso() -> str:
    """Return a timezone-aware timestamp suitable for JSON persistence."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_memory_document() -> dict[str, Any]:
    return {
        "version": 2,
        "users": {},
        "servers": {},
        "social_graph": {"users": {}, "servers": {}},
    }


def default_user(name: str = "", server_id: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": name,
        "nickname": "",
        "bot_opinion": "",
        "last_seen": now_iso(),
        "server_id": server_id,
    }
    data.update({category: [] for category in MEMORY_CATEGORIES})
    return data


def default_server(name: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "summary": "",
        "activity": 0.0,
        "mood": 0.0,
        "interesting_users": [],
        "last_activity": now_iso(),
        "last_interaction": "",
    }


@dataclass(slots=True)
class MemoryCandidate:
    """A proposed memory before it is accepted by the validator."""

    content: str
    type: str = "fact"
    confidence: float = 0.4
    source: str = "user"
    subject_user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Any) -> "MemoryCandidate | None":
        if isinstance(value, MemoryCandidate):
            return value
        if not isinstance(value, dict):
            return None
        content = value.get("content", value.get("info", ""))
        if not isinstance(content, str):
            return None
        return cls(
            content=content,
            type=str(value.get("type", "fact") or "fact").lower(),
            confidence=value.get("confidence", 0.4),
            source=str(value.get("source", "user") or "user").lower(),
            subject_user_id=(
                str(value["subject_user_id"])
                if value.get("subject_user_id") is not None
                else None
            ),
            metadata=dict(value.get("metadata", {}))
            if isinstance(value.get("metadata", {}), dict)
            else {},
        )
