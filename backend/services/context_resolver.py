from __future__ import annotations

import re

from backend.models import AuthorType, ConversationMessage, ContextReason

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'\)]+")

_DIAGNOSTIC_PHRASES = [
    "this works",
    "this is broken",
    "can you try",
    "this example fails",
    "try this",
    "here is",
    "this should",
    "not working",
    "doesn't work",
]


def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text).strip()


class ContextResolver:
    def resolve(
        self,
        extracted_url: dict,
        messages: list[ConversationMessage],
    ) -> dict:
        msg_id = extracted_url["message_id"]
        sorted_msgs = sorted(messages, key=lambda m: m.created_at)

        current: ConversationMessage | None = None
        previous: ConversationMessage | None = None
        for i, m in enumerate(sorted_msgs):
            if m.id == msg_id:
                current = m
                previous = sorted_msgs[i - 1] if i > 0 else None
                break

        if current is None:
            return {
                "selected_context_text": "",
                "selected_context_message_id": "",
                "selected_context_author_type": "",
                "selected_context_reason": ContextReason.NO_CONTEXT_AVAILABLE.value,
            }

        current_clean = _strip_urls(current.body_text)
        is_bare = extracted_url.get("is_bare_url", False)
        prev_text = _strip_urls(previous.body_text) if previous else ""

        if is_bare or len(current_clean) < 10:
            if previous and len(prev_text) > 20:
                return self._result(
                    previous, prev_text, ContextReason.BARE_URL_FALLBACK_TO_PREVIOUS
                )
            text = current_clean or prev_text
            source = current if current_clean else previous
            if source is None:
                source = current
            return self._result(source, text, ContextReason.NO_CONTEXT_AVAILABLE)

        if current.author_type in (AuthorType.USER, AuthorType.LEAD):
            if len(current_clean) > 20:
                return self._result(
                    current,
                    current_clean,
                    ContextReason.CURRENT_MESSAGE_HAS_MEANINGFUL_TEXT,
                )

        if current.author_type in (AuthorType.ADMIN, AuthorType.FIN):
            lower = current_clean.lower()
            has_diagnostic = any(phrase in lower for phrase in _DIAGNOSTIC_PHRASES)
            if has_diagnostic:
                return self._result(
                    current, current_clean, ContextReason.ADMIN_MESSAGE_REFERENCES_LINK
                )
            if previous and len(prev_text) > 20:
                return self._result(
                    previous,
                    prev_text,
                    ContextReason.PREVIOUS_MESSAGE_USED_DUE_TO_NEUTRAL,
                )

        if previous and prev_text:
            combined = f"{prev_text} {current_clean}".strip()
            return self._result(
                current,
                combined,
                ContextReason.COMBINED_CONTEXT_USED_DUE_TO_SPARSE_TEXT,
                message_id_override=current.id,
            )

        return self._result(
            current, current_clean, ContextReason.CURRENT_MESSAGE_HAS_MEANINGFUL_TEXT
        )

    @staticmethod
    def _result(
        msg: ConversationMessage,
        text: str,
        reason: ContextReason,
        *,
        message_id_override: str | None = None,
    ) -> dict:
        return {
            "selected_context_text": text,
            "selected_context_message_id": message_id_override or msg.id,
            "selected_context_author_type": msg.author_type.value,
            "selected_context_reason": reason.value,
        }
