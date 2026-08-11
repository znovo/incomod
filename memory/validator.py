"""Validation and normalization rules for candidate memories."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import MEMORY_TYPES, MemoryCandidate


_FILLER_MESSAGES = {
    "kkk",
    "kkkk",
    "kkkkk",
    "sim",
    "nao",
    "não",
    "ok",
    "beleza",
    "blz",
    "valeu",
    "obrigado",
    "obrigada",
}

_SPECULATIVE_MARKERS = re.compile(
    r"\b(acho|talvez|talvez|provavelmente|pode ser|nao sei|não sei|parece que|imagino)\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.strip().split()).casefold()


class MemoryValidator:
    """Reject low-value candidates and constrain what the LLM can persist."""

    allowed_sources = {"user", "observed", "llm", "legacy", "bot", "system"}

    def validate(
        self,
        candidate: Any,
        *,
        source_text: str = "",
        now: str | None = None,
    ) -> dict[str, Any] | None:
        parsed = MemoryCandidate.from_mapping(candidate)
        if parsed is None:
            return None

        content = " ".join(parsed.content.strip().split())
        normalized_content = normalize_text(content)
        if not normalized_content or len(normalized_content) < 3 or len(normalized_content) > 240:
            return None
        if normalized_content in _FILLER_MESSAGES:
            return None

        source_normalized = normalize_text(source_text)
        if source_normalized and (
            normalized_content == source_normalized
            or (len(source_normalized) >= 20 and source_normalized in normalized_content)
        ):
            # A memory must be a distilled claim, never a copied message.
            return None

        memory_type = parsed.type if parsed.type in MEMORY_TYPES else "fact"
        source = parsed.source if parsed.source in self.allowed_sources else "user"
        try:
            confidence = float(parsed.confidence)
        except (TypeError, ValueError):
            confidence = 0.4
        confidence = max(0.0, min(1.0, confidence))
        if _SPECULATIVE_MARKERS.search(normalized_content):
            confidence = min(confidence, 0.49)

        return {
            "content": content,
            "type": memory_type,
            "confidence": round(confidence, 3),
            "source": source,
            "created_at": now,
            "last_confirmed": now,
            "status": "hypothesis" if confidence < 0.5 else "active",
            "confirmation_count": 1,
            **(
                {"subject_user_id": parsed.subject_user_id}
                if parsed.subject_user_id
                else {}
            ),
        }
