from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

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
from backend.services.problem_summarizer import ProblemSummarizer
from backend.services.admin_url_builder import build_admin_url
from backend.classifiers.hybrid_classifier import HybridClassifier

logger = logging.getLogger(__name__)
router = APIRouter()

_cache = AnalysisCache()

_STATUS_ICON = {
    "working_example": "\U0001f7e2",
    "broken_example": "\U0001f534",
    "neutral_or_unknown": "\U00002753",
}

_TYPE_ICON = {
    "conversation": "\U0001f4ac",
    "workflow": "⚙️",
    "custom_action": "⚡",
    "article": "\U0001f4c4",
    "help_center": "\U0001f4d6",
    "loom": "\U0001f3ac",
    "github": "\U0001f4e6",
    "other": "\U0001f517",
}


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
        if url_type == "excluded":
            logger.info("Skipping excluded URL: %s", url_dict["url"])
            continue
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

    summarizer = ProblemSummarizer()
    problem_summary = summarizer.summarize(messages)

    return AnalysisResponse(
        conversation_id=conversation_id,
        summary=summary,
        links=links,
        groups=groups,
        problem_summary=problem_summary,
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

    summary = response.summary

    components.append({
        "type": "text",
        "text": (
            f"\U0001f7e2 Work {summary.working_count} | "
            f"\U0001f534 Broken {summary.broken_count} | "
            f"\U00002753 Unknown {summary.unknown_count}"
        ),
    })

    if response.problem_summary:
        truncated = response.problem_summary
        if len(truncated) > 200:
            truncated = truncated[:197] + "..."
        components.append({
            "type": "text",
            "text": f"*Problem:* {truncated}",
        })

    # current_filters = active_filters or set()
    # filter_buttons: list[dict[str, Any]] = []
    # for filter_id, label in [
    #     ("broken_only", "Broken only"),
    #     ("working_only", "Working only"),
    #     ("user_links", "User links"),
    #     ("admin_links", "Admin/Fin links"),
    #     ("workflows_only", "Workflows"),
    #     ("conversations_only", "Conversations"),
    # ]:
    #     style = "primary" if filter_id in current_filters else "secondary"
    #     filter_buttons.append({
    #         "type": "button",
    #         "label": label,
    #         "style": style,
    #         "id": filter_id,
    #         "action": {"type": "submit"},
    #     })

    

    # for btn in filter_buttons:
    #     components.append(btn)
    components.append({"type": "divider"})

    if not response.links:
        components.append({
            "type": "text",
            "text": "No links found in this conversation.",
        })
        return {"canvas": {"content": {"components": components}}}

    intercom_links = [l for l in response.links if l.url_type != "other"]
    other_links = [l for l in response.links if l.url_type == "other"]

    if intercom_links:
        grouper = Grouper()
        _, intercom_groups = grouper.group_by_status(intercom_links)

        status_order = ["broken_example", "working_example", "neutral_or_unknown"]
        ordered_groups = sorted(
            intercom_groups,
            key=lambda g: (
                status_order.index(g.example_status)
                if g.example_status in status_order
                else len(status_order)
            ),
        )

        for i, group in enumerate(ordered_groups):
            status_icon = _STATUS_ICON.get(group.example_status, "\U00002753")
            status_label = group.example_status.replace("_", " ").title()
            components.append({
                "type": "text",
                "text": f"{status_icon} *{status_label}* ({summary[i]})",
            })
            components.append({"type": "spacer", "size": "xs"})

            for link in group.items:
                link_url = link.url
                path = urlparse(link_url).path
                item_id = path.split("/")[-1] if path.split("/") else ""
                admin_url = build_admin_url(link_url, link.url_type)
                type_icon = _TYPE_ICON.get(link.url_type, "\U0001f517")
                type_label = link.url_type.replace("_", " ").title()
                confidence_pct = f"{link.confidence:.0%}"

                components.append({
                    "type": "text",
                    "text": f"{type_icon} *{type_label}* [{item_id}]({admin_url}) \u2014 {confidence_pct} - [app]({link_url})",
                })

                # link_parts = [f"[app]({link_url})"]
                # if admin_url:
                #     link_parts.append(f"[Admin]({admin_url})")
                # components.append({
                #     "type": "text",
                #     "text": "  \u00b7  ".join(link_parts),
                #     "style": "muted",
                # })
                components.append({"type": "spacer", "size": "xs"})

            components.append({"type": "spacer", "size": "s"})

    if other_links:
        components.append({"type": "divider"})
        components.append({
            "type": "text",
            "text": "\U0001f517 *Other Links*",
        })
        components.append({"type": "spacer", "size": "xs"})

        for link in other_links:
            hostname = urlparse(link.url).hostname or ""
            components.append({
                "type": "text",
                "text": f"[{hostname}]({link.url})",
            })
            components.append({"type": "spacer", "size": "xs"})

    components.append({"type": "spacer", "size": "m"})
    components.append({
        "type": "button",
        "label": "Refresh",
        "style": "secondary",
        "id": "refresh",
        "action": {"type": "submit"},
    })

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
    conversation = body.get("conversation") or {}
    if isinstance(conversation, dict):
        cid = conversation.get("id") or conversation.get("conversation_id")
        if cid:
            return str(cid)

    context = body.get("context") or {}
    if isinstance(context, dict):
        cid = context.get("conversation_id") or context.get("conversation", {}).get(
            "id"
        )
        if cid:
            return str(cid)

    cid = body.get("conversation_id")
    if cid:
        return str(cid)

    logger.warning("No conversation_id found. Payload keys: %s", list(body.keys()))
    return None


@router.post("/canvas/initialize")
async def canvas_initialize(body: dict[str, Any]) -> dict[str, Any]:
    try:
        conversation_id = _extract_conversation_id(body)
        if not conversation_id:
            return _error_canvas("Error: No conversation_id found in payload.")

        response = _analyze_conversation(conversation_id)
        return _build_canvas(response)
    except Exception as exc:
        logger.exception("canvas_initialize failed")
        return _error_canvas(f"Error: {type(exc).__name__}: {exc}")


@router.post("/canvas/submit")
async def canvas_submit(body: dict[str, Any]) -> dict[str, Any]:
    try:
        logger.info("Canvas submit payload: %s", body)

        conversation_id = _extract_conversation_id(body)
        if not conversation_id:
            return _error_canvas("Error: No conversation_id found in payload.")

        clicked = (
            body.get("component_id")
            or body.get("id")
            or body.get("input_values", {}).get("component_id")
            or ""
        )
        logger.info("Submit clicked=%s conversation=%s", clicked, conversation_id)

        if clicked == "refresh":
            _cache.invalidate(conversation_id)

        stored = body.get("stored_data", {})
        active_filters: set[str] = set(stored.get("current_filters", []))

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
    except Exception as exc:
        logger.exception("canvas_submit failed")
        return _error_canvas(f"Error: {type(exc).__name__}: {exc}")
