"""Deterministic, explainable autonomous decision engine."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Iterable

from .cooldown import CooldownManager
from .intentions import Intention


@dataclass(slots=True)
class Decision:
    action: str = "do_nothing"
    reason: str = "Não há uma interação segura e relevante agora."
    priority: float = 1.0
    target_type: str = ""
    user_id: str = ""
    server_id: str = ""
    channel_id: str = ""
    candidate_score: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "priority": round(self.priority, 3),
            "target_type": self.target_type,
            "user_id": self.user_id,
            "server_id": self.server_id,
            "channel_id": self.channel_id,
            "candidate_score": round(self.candidate_score, 3),
            "context": self.context,
        }


class DecisionEngine:
    """Chooses whether to act and a real target from observed candidates."""

    def __init__(
        self,
        *,
        rng: random.Random | None = None,
        action_threshold: float = 0.68,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.action_threshold = max(0.0, min(1.0, action_threshold))
        self.weights = weights or {
            "relationship": 0.30,
            "recency": 0.15,
            "shared_interest": 0.15,
            "conversational_interest": 0.20,
            "inactivity": 0.10,
            "controlled_randomness": 0.10,
        }

    def score_candidate(self, candidate: dict[str, Any]) -> float:
        values = {
            key: self._number(candidate.get(key, 0.0))
            for key in self.weights
        }
        values["controlled_randomness"] = self.rng.random()
        score = sum(self.weights[key] * values[key] for key in self.weights)
        return round(max(0.0, min(1.0, score)), 3)

    def generate_intentions(self, observation: dict[str, Any]) -> list[Intention]:
        intentions = [
            Intention(
                type="do_nothing",
                reason="Não há evidência suficiente para iniciar uma interação.",
                priority=0.82,
            )
        ]
        candidates = observation.get("candidates", [])
        channels = observation.get("channels", [])
        if not isinstance(candidates, list):
            candidates = []
        if not isinstance(channels, list):
            channels = []

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            score = self.score_candidate(candidate)
            user_id = str(candidate.get("user_id", ""))
            server_id = str(candidate.get("server_id", ""))
            channel_id = str(candidate.get("channel_id", ""))
            name = candidate.get("user_name") or user_id
            reason = self._reason(candidate, score)
            if candidate.get("dm_eligible", True):
                intentions.append(
                    Intention(
                        type="send_dm",
                        reason=f"{reason}; DM disponível para {name}",
                        priority=score * 0.9,
                        target_type="user",
                        user_id=user_id,
                        server_id=server_id,
                        channel_id=channel_id,
                        context={"candidate": candidate},
                    )
                )
            if channel_id:
                intentions.append(
                    Intention(
                        type="mention_user",
                        reason=f"{reason}; contexto de canal observável",
                        priority=score * 0.82,
                        target_type="user",
                        user_id=user_id,
                        server_id=server_id,
                        channel_id=channel_id,
                        context={"candidate": candidate},
                    )
                )

        for channel in channels:
            if not isinstance(channel, dict) or not channel.get("channel_id"):
                continue
            activity = self._number(channel.get("activity", 0.0))
            if activity < 0.35:
                continue
            intentions.append(
                Intention(
                    type="comment_in_channel",
                    reason="O canal tem atividade recente observável.",
                    priority=min(0.8, 0.35 + activity * 0.35),
                    target_type="channel",
                    server_id=str(channel.get("server_id", "")),
                    channel_id=str(channel["channel_id"]),
                    context={"channel": channel},
                )
            )
        return intentions

    def evaluate_intentions(
        self,
        intentions: Iterable[Intention],
        *,
        cooldowns: CooldownManager | None = None,
    ) -> list[Intention]:
        evaluated: list[Intention] = []
        for intention in intentions:
            if cooldowns and intention.type != "do_nothing":
                available = cooldowns.is_available(
                    intention.type,
                    server_id=intention.server_id,
                    user_id=intention.user_id,
                )
                if not available:
                    continue
            evaluated.append(intention)
        return sorted(evaluated, key=lambda item: item.priority, reverse=True)

    def select_target(self, intention: Intention) -> Decision:
        if intention.type == "do_nothing":
            return Decision(
                action="do_nothing",
                reason=intention.reason,
                priority=intention.priority,
            )
        candidate = intention.context.get("candidate", {})
        return Decision(
            action=intention.type,
            reason=intention.reason,
            priority=intention.priority,
            target_type=intention.target_type,
            user_id=intention.user_id,
            server_id=intention.server_id,
            channel_id=intention.channel_id,
            candidate_score=self._number(
                candidate.get("score", intention.priority) if isinstance(candidate, dict) else intention.priority
            ),
            context=intention.context,
        )

    def decide(
        self,
        observation: dict[str, Any],
        *,
        cooldowns: CooldownManager | None = None,
    ) -> Decision:
        intentions = self.generate_intentions(observation)
        for intention in intentions:
            if intention.type != "do_nothing":
                intention.priority = min(
                    1.0,
                    intention.priority
                    * self._number(observation.get("autonomy_factor", 1.0)),
                )
        evaluated = self.evaluate_intentions(intentions, cooldowns=cooldowns)
        if not evaluated:
            return Decision()
        selected = evaluated[0]
        if selected.type != "do_nothing" and selected.priority < self.action_threshold:
            return Decision(
                action="do_nothing",
                reason=(
                    f"A melhor intenção ({selected.type}) ficou abaixo do limite "
                    "de confiança/atividade."
                ),
                priority=1.0 - selected.priority,
            )
        decision = self.select_target(selected)
        if decision.action != "do_nothing" and not decision.user_id and decision.target_type == "user":
            return Decision(
                action="do_nothing",
                reason="A intenção não possui um usuário observado como alvo.",
                priority=1.0,
            )
        return decision

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _reason(candidate: dict[str, Any], score: float) -> str:
        parts = []
        if float(candidate.get("relationship", 0.0)) >= 0.45:
            parts.append("relação observada")
        if float(candidate.get("recency", 0.0)) >= 0.35:
            parts.append("atividade recente")
        if float(candidate.get("shared_interest", 0.0)) >= 0.2:
            parts.append("interesse compartilhado")
        if not parts:
            parts.append("contato observável")
        return f"{', '.join(parts)}; pontuação objetiva {score:.2f}"
