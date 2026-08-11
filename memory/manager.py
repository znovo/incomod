"""JSON-backed structured memory with migration and atomic persistence."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable

from .models import (
    MEMORY_CATEGORIES,
    TYPE_TO_CATEGORY,
    default_memory_document,
    default_server,
    default_user,
    now_iso,
)
from .validator import MemoryValidator, normalize_text


_NEGATION_WORDS = {"nao", "não", "nunca", "jamais", "sem", "mais"}
_STOP_WORDS = {
    "a",
    "o",
    "as",
    "os",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "um",
    "uma",
    "e",
    "que",
    "é",
    "em",
    "no",
    "na",
    "com",
    "para",
    "por",
    "eu",
    "meu",
    "minha",
}


def _tokens(value: str, *, remove_negation: bool = False) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode("ascii").casefold()
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    words = set(normalized.split()) - _STOP_WORDS
    if remove_negation:
        words -= {word.replace("não", "nao") for word in _NEGATION_WORDS}
        words -= _NEGATION_WORDS
    # A tiny Portuguese normalization handles common forms without an NLP dependency.
    replacements = {
        "gosto": "gosta",
        "gostava": "gosta",
        "gostei": "gosta",
        "gostam": "gosta",
        "curte": "curtir",
    }
    return {replacements.get(word, word) for word in words}


def _similarity(left: str, right: str) -> float:
    a = _tokens(left, remove_negation=True)
    b = _tokens(right, remove_negation=True)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_negated(value: str) -> bool:
    return bool(_tokens(value) & {"nao", "não", "nunca", "jamais", "sem"})


class JsonMemoryRepository:
    """Storage adapter; the rest of the application does not depend on JSON."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_user_items: int = 8,
        validator: MemoryValidator | None = None,
        clock: Callable[[], str] = now_iso,
        logger: logging.Logger | None = None,
    ) -> None:
        self.path = Path(path)
        self.max_user_items = max(1, int(max_user_items))
        self.validator = validator or MemoryValidator()
        self.clock = clock
        self.logger = logger or logging.getLogger(__name__)
        self._lock = threading.RLock()
        self.data: dict[str, Any] = default_memory_document()
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self) -> dict[str, Any]:
        with self._lock:
            migrated = False
            if not self.path.exists() or self.path.stat().st_size == 0:
                self.data = default_memory_document()
                self._loaded = True
                self.save()
                return self.data

            try:
                with self.path.open("r", encoding="utf-8") as stream:
                    raw = json.load(stream)
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                self.logger.exception("Falha ao carregar memória: %s", exc)
                self.data = default_memory_document()
                self._loaded = True
                self.save()
                return self.data

            self.data, migrated = self._normalize_document(raw)
            self._loaded = True
            if migrated:
                self.save()
            return self.data

    def save(self) -> None:
        with self._lock:
            snapshot = copy.deepcopy(self.data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_name: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=str(self.path.parent),
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_name = temporary.name
                    json.dump(snapshot, temporary, ensure_ascii=False, indent=2)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, self.path)
            except Exception:
                if temporary_name:
                    try:
                        os.unlink(temporary_name)
                    except OSError:
                        pass
                raise

    def get_user(self, user_id: str, user_name: str = "", server_id: str = "") -> dict[str, Any]:
        with self._lock:
            users = self.data.setdefault("users", {})
            key = str(user_id)
            if not isinstance(users.get(key), dict):
                users[key] = default_user(user_name, server_id)
            user = users[key]
            self._normalize_user_in_place(user, user_name, server_id)
            if user_name:
                user["name"] = user_name
            if server_id:
                user["server_id"] = server_id
            return user

    def get_server(self, server_id: str, server_name: str = "") -> dict[str, Any]:
        with self._lock:
            servers = self.data.setdefault("servers", {})
            key = str(server_id)
            if not isinstance(servers.get(key), dict):
                servers[key] = default_server(server_name)
            server = servers[key]
            self._normalize_server_in_place(server, server_name)
            if server_name:
                server["name"] = server_name
            return server

    def add_candidates(
        self,
        user_id: str,
        user_name: str,
        candidates: Iterable[Any],
        *,
        source_text: str = "",
        server_id: str = "",
        persist: bool = False,
    ) -> list[dict[str, Any]]:
        accepted: list[dict[str, Any]] = []
        with self._lock:
            user = self.get_user(user_id, user_name, server_id)
            timestamp = self.clock()
            for raw_candidate in candidates:
                candidate = self.validator.validate(
                    raw_candidate,
                    source_text=source_text,
                    now=timestamp,
                )
                if candidate is None:
                    continue
                if self._upsert_candidate(user, candidate):
                    accepted.append(candidate)
            self._trim_user(user)
            if persist and accepted:
                self.save()
        return accepted

    def update_opinion(
        self,
        user_id: str,
        user_name: str,
        opinion: str,
        *,
        server_id: str = "",
        persist: bool = False,
    ) -> list[dict[str, Any]]:
        return self.add_candidates(
            user_id,
            user_name,
            [
                {
                    "content": opinion,
                    "type": "opinion",
                    "confidence": 0.7,
                    "source": "bot",
                }
            ],
            server_id=server_id,
            persist=persist,
        )

    def touch_user(
        self,
        user_id: str,
        *,
        user_name: str = "",
        server_id: str = "",
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            user = self.get_user(user_id, user_name, server_id)
            user["last_seen"] = timestamp or self.clock()
            return user

    def touch_server(
        self,
        server_id: str,
        *,
        server_name: str = "",
        interaction: bool = False,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            server = self.get_server(server_id, server_name)
            server["last_activity"] = timestamp or self.clock()
            server["activity"] = min(1.0, float(server.get("activity", 0.0)) * 0.9 + 0.1)
            if interaction:
                server["last_interaction"] = server["last_activity"]
            return server

    def relevant_memories(self, user_id: str, limit: int = 8) -> list[dict[str, Any]]:
        user = self.get_user(user_id)
        records = [
            item
            for category in MEMORY_CATEGORIES
            for item in user.get(category, [])
            if isinstance(item, dict) and item.get("status", "active") in {"active", "hypothesis"}
        ]
        records.sort(
            key=lambda item: (
                item.get("status") == "active",
                float(item.get("confidence", 0.0)),
                item.get("last_confirmed", ""),
            ),
            reverse=True,
        )
        return copy.deepcopy(records[: max(0, limit)])

    def build_context(
        self,
        user_id: str,
        *,
        server_id: str = "",
        limit: int = 8,
    ) -> str:
        user = self.get_user(user_id)
        server = self.get_server(server_id) if server_id else {}
        memory_lines = []
        for item in self.relevant_memories(user_id, limit=limit):
            label = "hipótese" if item.get("status") == "hypothesis" else "memória"
            memory_lines.append(
                f"- [{label}; confiança {item.get('confidence', 0):.2f}; "
                f"tipo {item.get('type', 'fact')}] {item.get('content', '')}"
            )
        return "\n".join(
            [
                "Contexto de longo prazo:",
                f"Usuário: {user.get('name', '')}",
                f"Apelido: {user.get('nickname') or '(sem apelido)'}",
                f"Opinião do bot: {user.get('bot_opinion') or '(sem opinião)'}",
                f"Última vez visto: {user.get('last_seen', '')}",
                f"Servidor: {server.get('name', '')}",
                f"Resumo do servidor: {server.get('summary') or '(sem resumo)'}",
                "Memórias:",
                "\n".join(memory_lines) if memory_lines else "- (sem memória)",
            ]
        )

    def _upsert_candidate(self, user: dict[str, Any], candidate: dict[str, Any]) -> bool:
        category = TYPE_TO_CATEGORY[candidate["type"]]
        records = user.setdefault(category, [])
        candidate_content = candidate["content"]
        for index, existing in enumerate(records):
            if not isinstance(existing, dict):
                continue
            if existing.get("type") != candidate["type"]:
                continue
            similarity = _similarity(existing.get("content", ""), candidate_content)
            if similarity < 0.65:
                continue

            existing_negated = _is_negated(existing.get("content", ""))
            candidate_negated = _is_negated(candidate_content)
            if existing_negated != candidate_negated:
                if (
                    candidate["confidence"] < float(existing.get("confidence", 0.0))
                    and candidate["source"] != "user"
                ):
                    candidate["status"] = "hypothesis"
                    candidate["contradicts"] = existing.get("content", "")
                    records.append(candidate)
                    return True
                candidate["created_at"] = existing.get(
                    "created_at", candidate["created_at"]
                )
                candidate["updated_at"] = self.clock()
                candidate["confirmation_count"] = int(
                    existing.get("confirmation_count", 1)
                ) + 1
                records[index] = candidate
                if candidate["type"] == "opinion":
                    user["bot_opinion"] = candidate["content"]
                return True

            existing["last_confirmed"] = candidate["last_confirmed"]
            existing["confirmation_count"] = int(
                existing.get("confirmation_count", 1)
            ) + 1
            existing["confidence"] = round(
                min(1.0, max(float(existing.get("confidence", 0.0)), candidate["confidence"]) + 0.02),
                3,
            )
            if existing.get("status") == "hypothesis" and existing["confidence"] >= 0.5:
                existing["status"] = "active"
            if existing["type"] == "opinion":
                user["bot_opinion"] = existing.get("content", "")
            return True

        records.append(candidate)
        if candidate["type"] == "opinion" and candidate["status"] == "active":
            user["bot_opinion"] = candidate["content"]
        return True

    def _trim_user(self, user: dict[str, Any]) -> None:
        records: list[tuple[str, int, dict[str, Any]]] = []
        for category in MEMORY_CATEGORIES:
            values = user.setdefault(category, [])
            for index, item in enumerate(values):
                if isinstance(item, dict):
                    records.append((category, index, item))
        if len(records) <= self.max_user_items:
            return

        records.sort(
            key=lambda item: (
                item[2].get("status") == "active",
                float(item[2].get("confidence", 0.0)),
                item[2].get("last_confirmed", ""),
            ),
            reverse=True,
        )
        keep = {(category, index) for category, index, _ in records[: self.max_user_items]}
        for category in MEMORY_CATEGORIES:
            user[category] = [
                item
                for index, item in enumerate(user.get(category, []))
                if (category, index) in keep
            ]

    def _normalize_user_in_place(
        self,
        user: dict[str, Any],
        user_name: str = "",
        server_id: str = "",
    ) -> None:
        for category in MEMORY_CATEGORIES:
            if not isinstance(user.get(category), list):
                user[category] = []
        if "last_seen" not in user:
            user["last_seen"] = self.clock()
        user.setdefault("name", user_name)
        user.setdefault("nickname", "")
        user.setdefault("bot_opinion", "")
        user.setdefault("server_id", server_id)

    def _normalize_server_in_place(self, server: dict[str, Any], server_name: str = "") -> None:
        defaults = default_server(server_name)
        for key, value in defaults.items():
            server.setdefault(key, value)
        try:
            server["activity"] = max(0.0, min(1.0, float(server["activity"])))
        except (TypeError, ValueError):
            server["activity"] = 0.0
        try:
            server["mood"] = max(-1.0, min(1.0, float(server["mood"])))
        except (TypeError, ValueError):
            server["mood"] = 0.0
        if not isinstance(server.get("interesting_users"), list):
            server["interesting_users"] = []

    def _normalize_document(self, raw: Any) -> tuple[dict[str, Any], bool]:
        raw_version = raw.get("version", 1) if isinstance(raw, dict) else 1
        migrated = (
            not isinstance(raw, dict)
            or not isinstance(raw_version, (int, float))
            or raw_version < 2
        )
        document = default_memory_document()
        if not isinstance(raw, dict):
            return document, True

        for key in ("users", "servers"):
            if isinstance(raw.get(key), dict):
                document[key] = copy.deepcopy(raw[key])
        if isinstance(raw.get("social_graph"), dict):
            document["social_graph"] = copy.deepcopy(raw["social_graph"])
        elif isinstance(raw.get("social"), dict):
            document["social_graph"] = copy.deepcopy(raw["social"])
            migrated = True

        timestamp = self.clock()
        for user_id, raw_user in list(document["users"].items()):
            if not isinstance(raw_user, dict):
                document["users"][user_id] = default_user()
                migrated = True
                continue
            legacy_memory = raw_user.pop("memory", [])
            self._normalize_user_in_place(raw_user)
            if isinstance(legacy_memory, list):
                for value in legacy_memory:
                    content = value if isinstance(value, str) else value.get("content", "") if isinstance(value, dict) else ""
                    if not content:
                        continue
                    raw_user["facts"].append(
                        {
                            "content": normalize_text(content),
                            "type": "fact",
                            "confidence": 0.45,
                            "source": "legacy",
                            "created_at": timestamp,
                            "last_confirmed": timestamp,
                            "status": "hypothesis",
                            "confirmation_count": 1,
                        }
                    )
                    migrated = True
            opinion = raw_user.get("bot_opinion")
            if isinstance(opinion, str) and opinion.strip() and not raw_user["opinions"]:
                raw_user["opinions"].append(
                    {
                        "content": normalize_text(opinion),
                        "type": "opinion",
                        "confidence": 0.6,
                        "source": "legacy",
                        "created_at": timestamp,
                        "last_confirmed": timestamp,
                        "status": "active",
                        "confirmation_count": 1,
                    }
                )
                migrated = True

        for server_id, raw_server in list(document["servers"].items()):
            if not isinstance(raw_server, dict):
                document["servers"][server_id] = default_server()
                migrated = True
                continue
            before = copy.deepcopy(raw_server)
            self._normalize_server_in_place(raw_server)
            migrated = migrated or before != raw_server

        if raw.get("version") != 2:
            migrated = True
        document["version"] = 2
        return document, migrated


MemoryManager = JsonMemoryRepository
