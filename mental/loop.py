"""Periodic autonomous loop with explicit lifecycle and dry-run support."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .cooldown import CooldownManager
from .decision import Decision, DecisionEngine


Observer = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]
MessageGenerator = Callable[[Decision, dict[str, Any]], str | Awaitable[str]]


class MentalLoop:
    def __init__(
        self,
        *,
        bot: Any,
        observer: Observer,
        decision_engine: DecisionEngine,
        cooldowns: CooldownManager,
        executor: Any,
        message_generator: MessageGenerator,
        interval: float = 60.0,
        enabled: bool = True,
        dry_run: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bot = bot
        self.observer = observer
        self.decision_engine = decision_engine
        self.cooldowns = cooldowns
        self.executor = executor
        self.message_generator = message_generator
        self.interval = max(1.0, float(interval))
        self.enabled = enabled
        self.dry_run = dry_run
        self.logger = logger or logging.getLogger(__name__)
        self._task: asyncio.Task[Any] | None = None
        self._stop_event: asyncio.Event | None = None
        self._tick_lock: asyncio.Lock | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        if not self.enabled or self.running:
            return False
        self._stop_event = asyncio.Event()
        self._tick_lock = asyncio.Lock()
        self._task = asyncio.create_task(self._run(), name="incomod-mental-loop")
        self.logger.info("[MENTAL] Loop iniciado (intervalo=%ss, dry_run=%s)", self.interval, self.dry_run)
        return True

    async def stop(self) -> None:
        task = self._task
        if task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        if not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.logger.info("[MENTAL] Loop encerrado")

    async def tick(self) -> Decision:
        if not self.enabled or not self._bot_ready():
            return Decision(reason="Bot ainda não está conectado.")
        lock = self._tick_lock
        if lock is None:
            lock = asyncio.Lock()
            self._tick_lock = lock
        async with lock:
            self.logger.info("[MENTAL] Observando estado...")
            observation = self.observer()
            if inspect.isawaitable(observation):
                observation = await observation
            if not isinstance(observation, dict):
                return Decision(reason="Observação inválida; nenhuma ação executada.")

            decision = self.decision_engine.decide(observation, cooldowns=self.cooldowns)
            self.logger.info(
                "[MENTAL] Intenção: %s | prioridade: %.2f | alvo: %s",
                decision.action,
                decision.priority,
                decision.user_id or decision.channel_id or "nenhum",
            )
            if decision.action == "do_nothing":
                return decision

            available, scope, remaining = self.cooldowns.check(
                decision.action,
                server_id=decision.server_id,
                user_id=decision.user_id,
            )
            if not available:
                self.logger.info("[MENTAL] Cooldown ativo (%s, %.1fs)", scope, remaining)
                return Decision(
                    reason=f"Cooldown {scope} ativo por {remaining:.1f}s.",
                    priority=1.0,
                )

            if self.dry_run:
                self.logger.info(
                    "[MENTAL] DRY RUN: executaria %s para user=%s server=%s channel=%s",
                    decision.action,
                    decision.user_id or "-",
                    decision.server_id or "-",
                    decision.channel_id or "-",
                )
                self.cooldowns.mark(
                    decision.action,
                    server_id=decision.server_id,
                    user_id=decision.user_id,
                )
                return decision

            message = self.message_generator(decision, observation)
            if inspect.isawaitable(message):
                message = await message
            if not isinstance(message, str) or not message.strip():
                self.logger.info("[MENTAL] Mensagem vazia; convertendo para do_nothing")
                return Decision(reason="O gerador retornou mensagem vazia.")

            result = await self.executor.execute(decision, message)
            if getattr(result, "success", False):
                self.cooldowns.mark(
                    decision.action,
                    server_id=decision.server_id,
                    user_id=decision.user_id,
                )
                self.logger.info("[MENTAL] Ação concluída: %s", getattr(result, "reason", "ok"))
            else:
                self.logger.info("[MENTAL] Ação bloqueada: %s", getattr(result, "reason", "falha"))
            return decision

    async def _run(self) -> None:
        try:
            while self._stop_event is not None and not self._stop_event.is_set():
                try:
                    await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.exception("[MENTAL] Falha durante o ciclo")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    def _bot_ready(self) -> bool:
        try:
            return bool(self.bot.is_ready()) and self.bot.user is not None
        except Exception:
            return False
