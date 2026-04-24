from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from backend.config.settings import INTERCOM_API_TOKEN, USE_TRANSFORMER
from backend.models import (
    AnalysisResponse,
    AnalyzePreviewRequest,
    AnalyzeRequest,
    ConversationMessage,
    ExtractedLink,
)
from backend.services.conversation_provider import PreviewConversationProvider
from backend.services.intercom_api_provider import IntercomApiConversationProvider
from backend.services.url_extractor import UrlExtractor
from backend.services.url_categorizer import UrlCategorizer
from backend.services.context_resolver import ContextResolver
from backend.services.grouper import Grouper
from backend.services.cache import AnalysisCache
from backend.classifiers.hybrid_classifier import HybridClassifier

logger = logging.getLogger(__name__)
router = APIRouter()

_cache = AnalysisCache()


def _get_provider() -> IntercomApiConversationProvider:
    return IntercomApiConversationProvider()


def _run_pipeline(
    messages: list[ConversationMessage],
    conversation_id: str,
) -> AnalysisResponse:
    extractor = UrlExtractor()
    categorizer = UrlCategorizer()
    resolver = ContextResolver()
    classifier = HybridClassifier(use_transformer=USE_TRANSFORMER)
    grouper = Grouper()

    extracted_url_dicts = extractor.extract(messages)
    links: list[ExtractedLink] = []

    for url_dict in extracted_url_dicts:
        url_type = categorizer.categorize(url_dict["url"])
        context = resolver.resolve(url_dict, messages)
        fallback_used = context["selected_context_reason"] in (
            "bare_url_fallback_to_previous",
            "no_context_available",
        )
        status, confidence, signals = classifier.classify(
            context["selected_context_text"],
            fallback_used=fallback_used,
            url_type=url_type,
        )

        link = ExtractedLink(
            url=url_dict["url"],
            message_id=url_dict["message_id"],
            message_author_type=url_dict["message_author_type"],
            message_created_at=url_dict["message_created_at"],
            anchor_text=url_dict.get("anchor_text"),
            surrounding_text=url_dict["surrounding_text"],
            selected_context_text=context["selected_context_text"],
            selected_context_message_id=context["selected_context_message_id"],
            selected_context_author_type=context["selected_context_author_type"],
            selected_context_reason=context["selected_context_reason"],
            url_type=url_type,
            example_status=status.value,
            confidence=confidence,
            signals=signals,
        )
        links.append(link)

        logger.info(
            "Analyzed URL: url=%s type=%s status=%s confidence=%.2f reason=%s",
            link.url,
            link.url_type,
            link.example_status,
            link.confidence,
            link.selected_context_reason,
        )

    summary, groups = grouper.group_by_status(links)

    return AnalysisResponse(
        conversation_id=conversation_id,
        summary=summary,
        links=links,
        groups=groups,
    )


def _analyze_conversation(conversation_id: str) -> AnalysisResponse:
    cached = _cache.get(conversation_id)
    if cached is not None:
        logger.info("Cache hit for conversation %s", conversation_id)
        return cached

    provider = _get_provider()
    messages = provider.get_messages(conversation_id)
    response = _run_pipeline(messages, conversation_id)
    _cache.put(conversation_id, response)
    return response


FILTER_OPTIONS = {
    "broken_only": "broken_example",
    "working_only": "working_example",
    "unknown_only": "neutral_or_unknown",
}

AUTHOR_FILTERS = {
    "user_links": {"user", "lead"},
    "admin_links": {"admin", "fin"},
}

URL_TYPE_FILTERS = {
    "conversations_only": "conversation",
    "workflows_only": "workflow",
    "custom_actions_only": "custom_action",
}


def _apply_filters(
    response: AnalysisResponse, active_filters: set[str]
) -> AnalysisResponse:
    if not active_filters:
        return response

    filtered = list(response.links)

    status_filters = {FILTER_OPTIONS[f] for f in active_filters if f in FILTER_OPTIONS}
    if status_filters:
        filtered = [l for l in filtered if l.example_status in status_filters]

    for f in active_filters:
        if f in AUTHOR_FILTERS:
            allowed = AUTHOR_FILTERS[f]
            filtered = [l for l in filtered if l.message_author_type in allowed]

    type_filters = {
        URL_TYPE_FILTERS[f] for f in active_filters if f in URL_TYPE_FILTERS
    }
    if type_filters:
        filtered = [l for l in filtered if l.url_type in type_filters]

    grouper = Grouper()
    summary, groups = grouper.group_by_status(filtered)

    return AnalysisResponse(
        conversation_id=response.conversation_id,
        summary=summary,
        links=filtered,
        groups=groups,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze-conversation", response_model=AnalysisResponse)
async def analyze_conversation(request: AnalyzeRequest) -> AnalysisResponse:
    return _analyze_conversation(request.conversation_id)


@router.post("/analyze-preview", response_model=AnalysisResponse)
async def analyze_preview(request: AnalyzePreviewRequest) -> AnalysisResponse:
    provider = PreviewConversationProvider(request.messages)
    messages = provider.get_messages("")
    conversation_id = messages[0].conversation_id if messages else "preview"
    return _run_pipeline(messages, conversation_id)


def _build_canvas(
    response: AnalysisResponse, active_filters: set[str] | None = None
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []

    components.append({"type": "text", "text": "**Link Analysis**", "style": "header"})

    summary = response.summary
    components.append({
        "type": "text",
        "text": (
            f"\U0001f7e2 {summary.working_count} Working | "
            f"\U0001f534 {summary.broken_count} Broken | "
            f"⚪ {summary.unknown_count} Unknown"
        ),
    })

    components.append({"type": "divider"})

    current_filters = active_filters or set()
    filter_buttons: list[dict[str, Any]] = []
    for filter_id, label in [
        ("broken_only", "Broken only"),
        ("working_only", "Working only"),
        ("user_links", "User links"),
        ("admin_links", "Admin/Fin links"),
        ("workflows_only", "Workflows"),
        ("conversations_only", "Conversations"),
    ]:
        style = "primary" if filter_id in current_filters else "secondary"
        filter_buttons.append({
            "type": "button",
            "label": label,
            "style": style,
            "id": filter_id,
            "action": {"type": "submit"},
        })

    components.append({
        "type": "button",
        "label": "Refresh",
        "style": "secondary",
        "id": "refresh",
        "action": {"type": "submit"},
    })

    for btn in filter_buttons:
        components.append(btn)

    components.append({"type": "divider"})

    if not response.links:
        components.append({
            "type": "text",
            "text": "No links found in this conversation.",
        })
        return {"canvas": {"content": {"components": components}}}

    status_order = ["broken_example", "working_example", "neutral_or_unknown"]
    ordered_groups = sorted(
        response.groups,
        key=lambda g: (
            status_order.index(g.example_status)
            if g.example_status in status_order
            else len(status_order)
        ),
    )

    for i, group in enumerate(ordered_groups):
        group_label = group.example_status.replace("_", " ").title()
        components.append({
            "type": "text",
            "text": f"**{group_label} ({len(group.items)})**",
        })

        for link in group.items:
            truncated_url = (link.url[:57] + "...") if len(link.url) > 60 else link.url
            components.append({
                "type": "text",
                "text": f"- {truncated_url} [{link.url_type}] {link.confidence:.0%}",
            })

            context_snippet = link.selected_context_text
            if len(context_snippet) > 120:
                context_snippet = context_snippet[:117] + "..."
            components.append({
                "type": "text",
                "text": context_snippet,
                "style": "paragraph",
            })

            components.append({
                "type": "text",
                "text": (
                    f"Context: {link.selected_context_reason} "
                    f"| Author: {link.selected_context_author_type}"
                ),
                "style": "muted",
            })

        if i < len(ordered_groups) - 1:
            components.append({"type": "divider"})

    return {"canvas": {"content": {"components": components}}}


def _error_canvas(message: str) -> dict[str, Any]:
    return {
        "canvas": {
            "content": {
                "components": [{"type": "text", "text": message}]
            }
        }
    }


def _extract_conversation_id(body: dict[str, Any]) -> str | None:
    return body.get("conversation_id") or body.get("context", {}).get(
        "conversation_id"
    )


@router.post("/canvas/initialize")
async def canvas_initialize(body: dict[str, Any]) -> dict[str, Any]:
    conversation_id = _extract_conversation_id(body)
    if not conversation_id:
        return _error_canvas("Error: No conversation_id found in payload.")

    response = _analyze_conversation(conversation_id)
    return _build_canvas(response)


@router.post("/canvas/submit")
async def canvas_submit(body: dict[str, Any]) -> dict[str, Any]:
    conversation_id = _extract_conversation_id(body)
    if not conversation_id:
        return _error_canvas("Error: No conversation_id found in payload.")

    clicked = body.get("component_id", "")

    if clicked == "refresh":
        _cache.invalidate(conversation_id)

    active_filters: set[str] = set(body.get("current_filters", []))

    all_filter_ids = set(FILTER_OPTIONS) | set(AUTHOR_FILTERS) | set(URL_TYPE_FILTERS)
    if clicked in all_filter_ids:
        if clicked in active_filters:
            active_filters.discard(clicked)
        else:
            active_filters.add(clicked)

    response = _analyze_conversation(conversation_id)
    filtered = _apply_filters(response, active_filters)
    canvas = _build_canvas(filtered, active_filters)

    canvas["canvas"]["stored_data"] = {"current_filters": sorted(active_filters)}
    return canvas
