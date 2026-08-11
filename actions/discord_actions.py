"""Validated Discord action executor.

The decision engine produces data only. This module is the sole autonomous
path allowed to call Discord's send methods.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ActionResult:
    success: bool
    reason: str


class ActionExecutor:
    allowed_actions = {
        "send_dm",
        "mention_user",
        "comment_in_channel",
        "start_conversation",
        "ask_question",
        "react",
    }

    def __init__(
        self,
        bot: Any,
        *,
        blocked_user_ids: set[int] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bot = bot
        self.blocked_user_ids = blocked_user_ids or set()
        self.logger = logger or logging.getLogger(__name__)

    async def execute(self, decision: Any, message: str) -> ActionResult:
        action = str(getattr(decision, "action", "") or "")
        if action not in self.allowed_actions:
            return ActionResult(False, "ação não permitida")
        if not self._bot_ready():
            return ActionResult(False, "bot desconectado")

        text = str(message or "").strip()
        if not text:
            return ActionResult(False, "mensagem vazia")
        if len(text) > 2000:
            text = text[:1997].rstrip() + "..."

        user_id = self._snowflake(getattr(decision, "user_id", ""))
        if user_id is not None and self._is_blocked_user(user_id):
            return ActionResult(False, "usuário bloqueado ou bot")

        if action == "send_dm":
            if user_id is None:
                return ActionResult(False, "usuário inválido")
            user = self._resolve_user(user_id)
            if user is None:
                return ActionResult(False, "usuário não está disponível no cache")
            try:
                await user.send(text)
            except Exception as exc:
                self.logger.info("[MENTAL] DM não enviada: %s", exc)
                return ActionResult(False, "falha ao enviar DM")
            return ActionResult(True, "DM enviada")

        channel_id = self._snowflake(getattr(decision, "channel_id", ""))
        channel = self.bot.get_channel(channel_id) if channel_id is not None else None
        if channel is None or not hasattr(channel, "send"):
            return ActionResult(False, "canal não está disponível no cache")
        if not self._can_send(channel):
            return ActionResult(False, "bot não possui permissão para enviar no canal")

        if action == "mention_user":
            if user_id is None:
                return ActionResult(False, "usuário inválido")
            text = f"<@{user_id}> {text}"
        try:
            await channel.send(text)
        except Exception as exc:
            self.logger.info("[MENTAL] mensagem não enviada: %s", exc)
            return ActionResult(False, "falha ao enviar mensagem no canal")
        return ActionResult(True, "mensagem enviada no canal")

    def _bot_ready(self) -> bool:
        try:
            return bool(self.bot.is_ready()) and self.bot.user is not None
        except Exception:
            return False

    def _resolve_user(self, user_id: int) -> Any | None:
        user = self.bot.get_user(user_id)
        if user is not None:
            return user
        for guild in getattr(self.bot, "guilds", []):
            member = guild.get_member(user_id)
            if member is not None:
                return member
        return None

    def _is_blocked_user(self, user_id: int) -> bool:
        if user_id in self.blocked_user_ids:
            return True
        bot_user = getattr(self.bot, "user", None)
        if bot_user is not None and getattr(bot_user, "id", None) == user_id:
            return True
        resolved = self._resolve_user(user_id)
        return bool(resolved is not None and getattr(resolved, "bot", False))

    @staticmethod
    def _snowflake(value: Any) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _can_send(self, channel: Any) -> bool:
        # Permission lookup is optional for test doubles and DMs.
        try:
            guild = getattr(channel, "guild", None)
            current_user = getattr(guild, "me", None) or getattr(self.bot, "user", None)
            if current_user is not None and hasattr(channel, "permissions_for"):
                permissions = channel.permissions_for(current_user)
                return bool(getattr(permissions, "send_messages", False))
        except Exception:
            return False
        return True
