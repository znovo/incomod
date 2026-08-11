"""Translate the existing LLM tool response into memory candidates."""

from __future__ import annotations

from typing import Any

from .models import MemoryCandidate


class MemoryExtractor:
    """Extract structured candidates without persisting anything."""

    def extract(self, response: Any) -> list[MemoryCandidate]:
        if not isinstance(response, dict):
            return []

        tools = response.get("tool", response.get("tools", []))
        if isinstance(tools, dict):
            tools = [tools]
        if not isinstance(tools, list):
            return []

        candidates: list[MemoryCandidate] = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name")
            arguments = tool.get("arguments", {})
            if not isinstance(arguments, dict):
                continue

            if name == "extract_memory":
                candidate = MemoryCandidate.from_mapping(
                    {
                        "content": arguments.get(
                            "content", arguments.get("info", "")
                        ),
                        "type": arguments.get("type", "fact"),
                        "confidence": arguments.get("confidence", 0.4),
                        "source": arguments.get("source", "user"),
                        "subject_user_id": arguments.get("subject_user_id"),
                    }
                )
                if candidate is not None:
                    candidates.append(candidate)
            elif name == "update_opinion":
                opinion = arguments.get("opinion", "")
                if isinstance(opinion, str) and opinion.strip():
                    candidates.append(
                        MemoryCandidate(
                            content=opinion,
                            type="opinion",
                            confidence=0.7,
                            source="bot",
                        )
                    )
        return candidates
