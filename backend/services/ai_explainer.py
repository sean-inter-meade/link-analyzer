from __future__ import annotations

import logging

import httpx

from backend.config.settings import OPENAI_API_KEY
from backend.models import AnalysisResponse, ConversationMessage

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a technical support analyst at Intercom. You help agents understand \
customer issues by analyzing conversation data and link classifications.

You will receive:
1. The conversation messages between the customer and support team
2. A link analysis showing which shared links are working, broken, or unknown

Produce two sections separated by the exact marker "---CUSTOMER_MESSAGE---":

SECTION 1 (Internal note for the support agent):
Write 1-2 paragraphs explaining what the customer's issue appears to be, \
which links are broken vs working, and what this likely means. Be concise \
and actionable.

SECTION 2 (Draft message to the customer):
Write a friendly, professional message to the customer that:
- Summarizes your understanding of their issue
- References the specific broken/working items you found
- Asks the customer to confirm if your understanding is correct
- Keep it conversational and empathetic

Do NOT include the section labels in your output, just the content separated \
by the marker.\
"""


def _build_user_prompt(
    messages: list[ConversationMessage],
    analysis: AnalysisResponse,
) -> str:
    parts: list[str] = []

    parts.append("## Conversation Messages\n")
    for msg in messages:
        parts.append(f"[{msg.author_type.value}]: {msg.body_text}\n")

    parts.append("\n## Link Analysis\n")
    if analysis.problem_summary:
        parts.append(f"Detected problem: {analysis.problem_summary}\n")

    for link in analysis.links:
        status_label = link.example_status.replace("_", " ")
        type_label = link.url_type.replace("_", " ")
        parts.append(f"- {type_label}: {link.url} -> {status_label} ({link.confidence:.0%} confidence)")
        if link.selected_context_text:
            ctx = link.selected_context_text[:150]
            parts.append(f"  Context: {ctx}")
        parts.append("")

    return "\n".join(parts)


class AiExplainer:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or OPENAI_API_KEY

    def generate(
        self,
        messages: list[ConversationMessage],
        analysis: AnalysisResponse,
    ) -> tuple[str, str]:
        if not self._api_key:
            return (
                "OpenAI API key not configured. Set OPENAI_API_KEY in your environment.",
                "",
            )

        user_prompt = _build_user_prompt(messages, analysis)

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    _OPENAI_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.4,
                        "max_tokens": 1000,
                    },
                )
                response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"] or ""
            return _split_response(content)
        except Exception:
            logger.exception("OpenAI API call failed")
            return ("Failed to generate explanation. Check logs for details.", "")


def _split_response(content: str) -> tuple[str, str]:
    marker = "---CUSTOMER_MESSAGE---"
    if marker in content:
        parts = content.split(marker, 1)
        return parts[0].strip(), parts[1].strip()
    return content.strip(), ""
