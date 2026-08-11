"""Intentions are data; they do not perform Discord operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Intention:
    type: str
    reason: str
    priority: float
    target_type: str = ""
    user_id: str = ""
    server_id: str = ""
    channel_id: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "reason": self.reason,
            "priority": round(max(0.0, min(1.0, self.priority)), 3),
            "target_type": self.target_type,
            "user_id": self.user_id,
            "server_id": self.server_id,
            "channel_id": self.channel_id,
            "context": self.context,
        }
