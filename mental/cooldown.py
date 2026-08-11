"""Centralized cooldowns for autonomous actions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CooldownConfig:
    global_seconds: float = 120.0
    server_seconds: float = 300.0
    user_seconds: float = 1800.0
    dm_seconds: float = 1800.0
    action_seconds: dict[str, float] = field(
        default_factory=lambda: {
            "send_dm": 1800.0,
            "mention_user": 300.0,
            "comment_in_channel": 300.0,
            "ask_question": 300.0,
            "start_conversation": 300.0,
            "react": 120.0,
        }
    )


class CooldownManager:
    """In-memory monotonic cooldown registry.

    Cooldowns intentionally do not use wall-clock timestamps: a restart clears
    them, which is safer than persisting a stale lockout or accidentally
    allowing an action because the system clock moved backwards.
    """

    def __init__(self, config: CooldownConfig | None = None, *, clock=time.monotonic) -> None:
        self.config = config or CooldownConfig()
        self.clock = clock
        self._global_until = 0.0
        self._servers: dict[str, float] = {}
        self._users: dict[str, float] = {}
        self._actions: dict[str, float] = {}

    def check(
        self,
        action: str,
        *,
        server_id: str = "",
        user_id: str = "",
        now: float | None = None,
    ) -> tuple[bool, str, float]:
        current = self.clock() if now is None else now
        checks = [
            ("global", self._global_until),
            ("server", self._servers.get(str(server_id), 0.0) if server_id else 0.0),
            ("user", self._users.get(str(user_id), 0.0) if user_id else 0.0),
            ("action", self._actions.get(action, 0.0)),
        ]
        if action == "send_dm" and user_id:
            checks.append(("dm", self._users.get(f"dm:{user_id}", 0.0)))
        for scope, until in checks:
            if until > current:
                return False, scope, round(until - current, 3)
        return True, "", 0.0

    def is_available(
        self,
        action: str,
        *,
        server_id: str = "",
        user_id: str = "",
        now: float | None = None,
    ) -> bool:
        return self.check(action, server_id=server_id, user_id=user_id, now=now)[0]

    def mark(
        self,
        action: str,
        *,
        server_id: str = "",
        user_id: str = "",
        now: float | None = None,
    ) -> None:
        current = self.clock() if now is None else now
        self._global_until = current + max(0.0, self.config.global_seconds)
        if server_id:
            self._servers[str(server_id)] = current + max(0.0, self.config.server_seconds)
        if user_id:
            self._users[str(user_id)] = current + max(0.0, self.config.user_seconds)
        action_duration = self.config.action_seconds.get(action, 0.0)
        self._actions[action] = current + max(0.0, action_duration)
        if action == "send_dm" and user_id:
            self._users[f"dm:{user_id}"] = current + max(0.0, self.config.dm_seconds)

    def remaining(
        self,
        action: str,
        *,
        server_id: str = "",
        user_id: str = "",
        now: float | None = None,
    ) -> float:
        return self.check(action, server_id=server_id, user_id=user_id, now=now)[2]

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        current = self.clock() if now is None else now
        return {
            "global": max(0.0, self._global_until - current),
            "servers": {key: max(0.0, value - current) for key, value in self._servers.items()},
            "users": {key: max(0.0, value - current) for key, value in self._users.items()},
            "actions": {key: max(0.0, value - current) for key, value in self._actions.items()},
        }
