from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from backend.config.settings import INTERCOM_API_BASE, INTERCOM_API_TOKEN
from backend.models import AuthorType, ConversationMessage
from backend.services.conversation_provider import ConversationProvider, _strip_html

logger = logging.getLogger(__name__)

_AUTHOR_TYPE_MAP: dict[str, AuthorType] = {
    "user": AuthorType.USER,
    "lead": AuthorType.LEAD,
    "admin": AuthorType.ADMIN,
    "bot": AuthorType.BOT,
    "fin": AuthorType.FIN,
}


class IntercomApiConversationProvider(ConversationProvider):
    def __init__(
        self,
        api_token: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self._api_token = api_token or INTERCOM_API_TOKEN
        self._api_base = (api_base or INTERCOM_API_BASE).rstrip("/")

    def get_messages(self, conversation_id: str) -> list[ConversationMessage]:
        if not self._api_token:
            logger.error("No Intercom API token configured; cannot fetch conversation %s", conversation_id)
            return []

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    f"{self._api_base}/conversations/{conversation_id}",
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Intercom-Version": "2.11",
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()

            data = response.json()
            messages: list[ConversationMessage] = []

            source = data.get("source", {})
            source_body = _strip_html(source.get("body", "") or "")
            source_author = source.get("author", {})
            source_id = str(source.get("id", "")) or f"{conversation_id}_source"

            messages.append(
                ConversationMessage(
                    id=source_id,
                    author_type=self._map_author_type(source_author.get("type", "")),
                    body_text=source_body,
                    created_at=datetime.fromtimestamp(data["created_at"], tz=timezone.utc),
                    conversation_id=conversation_id,
                )
            )

            parts = (
                data.get("conversation_parts", {})
                .get("conversation_parts", [])
            )
            for part in parts:
                body = _strip_html(part.get("body", "") or "")
                if not body:
                    continue

                author = part.get("author", {})
                messages.append(
                    ConversationMessage(
                        id=str(part["id"]),
                        author_type=self._map_author_type(author.get("type", "")),
                        body_text=body,
                        created_at=datetime.fromtimestamp(part["created_at"], tz=timezone.utc),
                        conversation_id=conversation_id,
                    )
                )

            messages.sort(key=lambda m: m.created_at)
            return messages

        except Exception:
            logger.exception("Failed to fetch conversation %s from Intercom API", conversation_id)
            return []

    def create_note(
        self,
        conversation_id: str,
        admin_id: str,
        body: str,
    ) -> bool:
        if not self._api_token:
            logger.error("No Intercom API token configured; cannot create note")
            return False

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self._api_base}/conversations/{conversation_id}/reply",
                    headers={
                        "Authorization": f"Bearer {self._api_token}",
                        "Intercom-Version": "2.11",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "message_type": "note",
                        "type": "admin",
                        "admin_id": admin_id,
                        "body": body,
                    },
                )
                response.raise_for_status()
                return True
        except Exception:
            logger.exception("Failed to create note on conversation %s", conversation_id)
            return False

    def _map_author_type(self, raw: str) -> AuthorType:
        return _AUTHOR_TYPE_MAP.get(raw.lower(), AuthorType.OTHER)
