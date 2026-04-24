from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from backend.models import AuthorType, ConversationMessage


class ConversationProvider(ABC):
    @abstractmethod
    def get_messages(self, conversation_id: str) -> list[ConversationMessage]:
        ...


class StubConversationProvider(ConversationProvider):
    def get_messages(self, conversation_id: str) -> list[ConversationMessage]:
        # TODO: replace with real Intercom API call
        return []


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_author_type(raw: str) -> AuthorType:
    try:
        return AuthorType(raw.lower())
    except ValueError:
        return AuthorType.OTHER


class PreviewConversationProvider(ConversationProvider):
    def __init__(self, raw_messages: list[dict]) -> None:
        self._messages = self._normalize(raw_messages)

    def get_messages(self, conversation_id: str) -> list[ConversationMessage]:
        return self._messages

    def _normalize(self, raw_messages: list[dict]) -> list[ConversationMessage]:
        messages: list[ConversationMessage] = []
        for raw in raw_messages:
            body = _strip_html(raw.get("body_text", "") or raw.get("body", "") or "")
            created_at = raw.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            elif isinstance(created_at, (int, float)):
                created_at = datetime.fromtimestamp(created_at, tz=timezone.utc)
            elif created_at is None:
                created_at = datetime.now(tz=timezone.utc)

            messages.append(
                ConversationMessage(
                    id=str(raw.get("id", "")),
                    author_type=_normalize_author_type(raw.get("author_type", "other")),
                    body_text=body,
                    created_at=created_at,
                    conversation_id=str(raw.get("conversation_id", "")),
                )
            )

        messages.sort(key=lambda m: m.created_at)
        return messages
