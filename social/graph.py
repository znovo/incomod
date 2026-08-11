"""A conservative social graph built only from observed interactions."""

from __future__ import annotations

import copy
import logging
import math
from datetime import datetime, timezone
from typing import Any, Iterable


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _age_days(value: str | None, now: datetime) -> float:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return 365.0
    return max(0.0, (now - parsed).total_seconds() / 86400)


class SocialGraph:
    """Maintains persisted, explainable interaction statistics."""

    def __init__(self, document: dict[str, Any], *, logger: logging.Logger | None = None) -> None:
        self.document = document
        self.logger = logger or logging.getLogger(__name__)
        graph = document.setdefault("social_graph", {})
        if not isinstance(graph, dict):
            graph = {"users": {}, "servers": {}}
            document["social_graph"] = graph
        graph.setdefault("users", {})
        graph.setdefault("servers", {})

    @property
    def users(self) -> dict[str, dict[str, Any]]:
        return self.document["social_graph"]["users"]

    @property
    def servers(self) -> dict[str, dict[str, Any]]:
        return self.document["social_graph"]["servers"]

    def observe_interaction(
        self,
        user_id: str,
        *,
        server_id: str = "",
        channel_id: str = "",
        user_name: str = "",
        is_direct: bool = False,
        is_bot: bool = False,
        shared_interests: Iterable[str] = (),
        now: str | None = None,
    ) -> dict[str, Any]:
        """Record an observation; no relationship label is invented."""

        if is_bot:
            return self.get_user(user_id)
        timestamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        key = str(user_id)
        record = self.get_user(key, user_name=user_name)
        record["interaction_count"] = int(record.get("interaction_count", 0)) + 1
        record["last_interaction"] = timestamp
        if user_name:
            record["name"] = user_name
        if server_id:
            record["last_server_id"] = str(server_id)
        if channel_id:
            record["last_channel_id"] = str(channel_id)
        if is_direct:
            record["direct_interaction_count"] = int(
                record.get("direct_interaction_count", 0)
            ) + 1

        history = record.setdefault("recent_interactions", [])
        if not isinstance(history, list):
            history = []
            record["recent_interactions"] = history
        history.append(timestamp)
        record["recent_interactions"] = history[-30:]
        interests = record.setdefault("shared_interests", [])
        for interest in shared_interests:
            if isinstance(interest, str) and interest.strip() and interest not in interests:
                interests.append(interest.strip())
        record["shared_interests"] = interests[-20:]
        record["conversation_frequency"] = self._frequency(record, timestamp)
        record["relationship_score"] = self._relationship_score(record, timestamp)
        record["relationship_type"] = self._relationship_type(record)
        return record

    def observe_server(
        self,
        server_id: str,
        *,
        channel_id: str = "",
        server_name: str = "",
        interaction: bool = False,
        now: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        record = self.get_server(server_id, server_name=server_name)
        record["last_activity"] = timestamp
        if interaction:
            record["last_interaction"] = timestamp
        if channel_id:
            channels = record.setdefault("active_channels", [])
            if channel_id not in channels:
                channels.append(str(channel_id))
            record["active_channels"] = channels[-20:]
        record["activity"] = min(1.0, float(record.get("activity", 0.0)) * 0.9 + 0.1)
        return record

    def get_user(self, user_id: str, *, user_name: str = "") -> dict[str, Any]:
        key = str(user_id)
        record = self.users.setdefault(
            key,
            {
                "name": user_name,
                "interaction_count": 0,
                "last_interaction": "",
                "conversation_frequency": 0.0,
                "relationship_score": 0.0,
                "relationship_type": "unknown",
                "shared_interests": [],
                "recent_interactions": [],
            },
        )
        if not isinstance(record, dict):
            record = {"name": user_name}
            self.users[key] = record
        record.setdefault("name", user_name)
        record.setdefault("interaction_count", 0)
        record.setdefault("last_interaction", "")
        record.setdefault("conversation_frequency", 0.0)
        record.setdefault("relationship_score", 0.0)
        record.setdefault("relationship_type", "unknown")
        record.setdefault("shared_interests", [])
        record.setdefault("recent_interactions", [])
        return record

    def get_server(self, server_id: str, *, server_name: str = "") -> dict[str, Any]:
        key = str(server_id)
        record = self.servers.setdefault(
            key,
            {
                "name": server_name,
                "activity": 0.0,
                "last_activity": "",
                "last_interaction": "",
                "active_channels": [],
            },
        )
        if not isinstance(record, dict):
            record = {"name": server_name}
            self.servers[key] = record
        record.setdefault("name", server_name)
        record.setdefault("activity", 0.0)
        record.setdefault("last_activity", "")
        record.setdefault("last_interaction", "")
        record.setdefault("active_channels", [])
        return record

    def candidate_snapshot(
        self,
        *,
        now: str | None = None,
        known_user_ids: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        now_dt = _parse_timestamp(now) or datetime.now(timezone.utc)
        allowed = {str(value) for value in known_user_ids}
        records: list[dict[str, Any]] = []
        for user_id, record in self.users.items():
            if allowed and user_id not in allowed:
                continue
            last_seen = record.get("last_interaction", "")
            age_days = _age_days(last_seen, now_dt)
            recency = max(0.0, min(1.0, math.exp(-age_days * 4)))
            inactivity = max(0.0, min(1.0, age_days / 7))
            frequency = max(0.0, min(1.0, float(record.get("conversation_frequency", 0.0))))
            records.append(
                {
                    "user_id": user_id,
                    "user_name": record.get("name", ""),
                    "relationship": max(0.0, min(1.0, float(record.get("relationship_score", 0.0)))),
                    "recency": recency,
                    "inactivity": inactivity,
                    "conversational_interest": frequency,
                    "shared_interest": min(1.0, len(record.get("shared_interests", [])) / 5),
                    "shared_interests": list(record.get("shared_interests", [])),
                    "last_interaction": last_seen,
                    "relationship_type": record.get("relationship_type", "unknown"),
                    "server_id": record.get("last_server_id", ""),
                    "channel_id": record.get("last_channel_id", ""),
                }
            )
        return records

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.document["social_graph"])

    @staticmethod
    def _frequency(record: dict[str, Any], timestamp: str) -> float:
        history = record.get("recent_interactions", [])
        if not history:
            return 0.0
        now = _parse_timestamp(timestamp) or datetime.now(timezone.utc)
        recent = sum(1 for item in history if _age_days(item, now) <= 7)
        return round(min(1.0, recent / 10), 3)

    @staticmethod
    def _relationship_score(record: dict[str, Any], timestamp: str) -> float:
        current = float(record.get("relationship_score", 0.0))
        count = int(record.get("interaction_count", 0))
        direct = int(record.get("direct_interaction_count", 0))
        base = min(0.65, count * 0.025) + min(0.25, direct * 0.05)
        age = _age_days(record.get("last_interaction"), _parse_timestamp(timestamp) or datetime.now(timezone.utc))
        decay = max(0.0, min(0.25, age / 30 * 0.25))
        return round(max(current, min(1.0, base)) - decay, 3)

    @staticmethod
    def _relationship_type(record: dict[str, Any]) -> str:
        count = int(record.get("interaction_count", 0))
        frequency = float(record.get("conversation_frequency", 0.0))
        if count == 0:
            return "unknown"
        if frequency >= 0.4 and count >= 4:
            return "frequent_contact"
        if count == 1:
            return "new_contact"
        if _age_days(record.get("last_interaction"), datetime.now(timezone.utc)) > 30:
            return "inactive_contact"
        return "unknown"
