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
from backend.services.correction_store import CorrectionStore

logger = logging.getLogger(__name__)
router = APIRouter()

_cache = AnalysisCache()

_extractor = UrlExtractor()
_categorizer = UrlCategorizer()
_resolver = ContextResolver()
_grouper = Grouper()
_classifier = HybridClassifier(use_transformer=USE_TRANSFORMER)
_summarizer = ProblemSummarizer()
_provider = IntercomApiConversationProvider()
_correction_store = CorrectionStore()

_STATUS_ICON = {
    "working_example": "\U0001f7e2",
    "broken_example": "\U0001f534",
    "unknown_or_neutral": "\U00002753",
}

_TYPE_ICON = {
    "conversation": "\U0001f4ac",
    "workflow": "⚙️",
    "custom_action": "⚡",
    "procedure": "\U0001f9ea",
    "guidance": "\U0001f9ed",
    "outbound": "\U0001f4e4",
    "knowledge_hub": "\U0001f4da",
    "series": "\U0001f504",
    "report": "\U0001f4ca",
    "user": "\U0001f464",
    "company": "\U0001f3e2",
    "article": "\U0001f4c4",
    "help_center": "\U0001f4d6",
    "loom": "\U0001f3ac",
    "github": "\U0001f4e6",
    "other": "\U0001f517",
}

_OUTBOUND_SUBTYPE_ICON = {
    "tour": "\U0001f9ed",
    "email": "\U00002709",
    "chat": "\U0001f4ac",
    "post": "\U0001f4cc",
    "push": "\U0001f514",
    "checklists": "\U00002611",
    "sms": "\U0001f4f1",
    "survey": "\U0001f4cb",
    "carousel": "\U0001f3a0",
    "custom-bot": "\U0001f916",
    "broadcast": "\U0001f4e2",
    "discord-broadcast": "\U0001f4e2",
    "tooltips": "\U0001f4a1",
    "whatsapp": "\U0001f4f2",
    "news-items": "\U0001f4f0",
    "news": "\U0001f4f0",
}

_RESOURCE_ID_KEYWORDS = ("users", "companies", "folder")
_ID_LIKE_RE = __import__("re").compile(r"^[0-9a-f]{16,}$|^\d+$")


def _extract_display_id(path_segments: list[str], url_type: str) -> str:
    for keyword in _RESOURCE_ID_KEYWORDS:
        if keyword in path_segments:
            idx = path_segments.index(keyword)
            if idx + 1 < len(path_segments):
                return path_segments[idx + 1]
    numeric = next((seg for seg in reversed(path_segments) if seg.isdigit()), None)
    if numeric:
        return numeric
    hex_id = next((seg for seg in reversed(path_segments) if _ID_LIKE_RE.match(seg)), None)
    if hex_id:
        return hex_id
    return path_segments[-1] if path_segments else ""


def _outbound_subtype_icon(path_segments: list[str]) -> str:
    if "outbound" in path_segments:
        idx = path_segments.index("outbound")
        if idx + 1 < len(path_segments):
            subtype = path_segments[idx + 1]
            return _OUTBOUND_SUBTYPE_ICON.get(subtype, "")
    return ""


def _get_provider() -> IntercomApiConversationProvider:
    return _provider


def _extract_admin(body: dict[str, Any]) -> tuple[str | None, str | None]:
    admin = body.get("admin") or {}
    admin_id = str(admin["id"]) if "id" in admin else None
    admin_email = admin.get("email")
    return admin_id, admin_email


def _run_pipeline(
    messages: list[ConversationMessage],
    conversation_id: str,
) -> AnalysisResponse:
    extractor = _extractor
    categorizer = _categorizer
    resolver = _resolver
    classifier = _classifier
    grouper = _grouper

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

    problem_summary = _summarizer.summarize(messages)

    return AnalysisResponse(
        conversation_id=conversation_id,
        summary=summary,
        links=links,
        groups=groups,
        problem_summary=problem_summary,
    )


def _apply_corrections(
    response: AnalysisResponse,
    correction_store: CorrectionStore | None = None,
) -> AnalysisResponse:
    store = correction_store or _correction_store
    corrections = store.get_corrections(response.conversation_id)
    if not corrections:
        return response

    for link in response.links:
        corrected_status = corrections.get(link.url)
        if corrected_status:
            link.example_status = corrected_status
            link.corrected = True

    summary, groups = _grouper.group_by_status(response.links)
    response.summary = summary
    response.groups = groups
    return response


def _analyze_conversation(conversation_id: str) -> AnalysisResponse:
    cached = _cache.get(conversation_id)
    if cached is not None:
        logger.info("Cache hit for conversation %s", conversation_id)
        return _apply_corrections(cached)

    provider = _get_provider()
    messages = provider.get_messages(conversation_id)
    response = _run_pipeline(messages, conversation_id)
    _cache.put(conversation_id, response)
    return _apply_corrections(response)


FILTER_OPTIONS = {
    "broken_only": "broken_example",
    "working_only": "working_example",
    "unknown_only": "unknown_or_neutral",
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

    # components.append({
    #     "type": "text",
    #     "text": (
    #         f"\U0001f7e2 Work {summary.working_count} | "
    #         f"\U0001f534 Broken {summary.broken_count} | "
    #         f"\U00002753 Unknown {summary.unknown_count}"
    #     ),
    # })

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

        status_order = ["broken_example", "working_example", "unknown_or_neutral"]
        ordered_groups = sorted(
            intercom_groups,
            key=lambda g: (
                status_order.index(g.example_status)
                if g.example_status in status_order
                else len(status_order)
            ),
        )

        for group in ordered_groups:
            status_icon = _STATUS_ICON.get(group.example_status, "\U00002753")
            status_label = group.example_status.replace("_", " ").title()

            components.append({
                "type": "text",
                "text": f"{status_icon} *{status_label}* ({len(group.items)})",
            })
            components.append({"type": "spacer", "size": "xs"})

            for link in group.items:
                link_url = link.url
                path = urlparse(link_url).path
                path_segments = path.strip("/").split("/") if path else []
                item_id = _extract_display_id(path_segments, link.url_type)
                admin_url = build_admin_url(link_url, link.url_type)
                type_icon = _TYPE_ICON.get(link.url_type, "\U0001f517")
                if link.url_type == "outbound":
                    sub_icon = _outbound_subtype_icon(path_segments)
                    if sub_icon:
                        type_icon = f"{type_icon}{sub_icon}"
                type_label = link.url_type.replace("_", " ").title()
                confidence_pct = f"{link.confidence:.0%}"

                edited_marker = " ✏️" if link.corrected else ""
                components.append({
                    "type": "button",
                    "label": f"{type_icon} {type_label} {item_id} ({confidence_pct}){edited_marker}",
                    "style": "link",
                    "id": f"correct:{link_url}",
                    "action": {"type": "submit"},
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

            components.append({"type": "divider"})

    if other_links:
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


def _build_detail_canvas(
    link: ExtractedLink,
    conversation_id: str,
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []

    status_icon = _STATUS_ICON.get(link.example_status, "\U00002753")
    status_label = link.example_status.replace("_", " ").title()
    type_label = link.url_type.replace("_", " ").title()
    edited_marker = " (edited)" if link.corrected else ""

    components.append({
        "type": "text",
        "text": f"*{type_label}*: [{link.url}]({link.url})",
    })
    components.append({
        "type": "text",
        "text": f"Current status: {status_icon} {status_label}{edited_marker}",
    })
    components.append({"type": "divider"})
    components.append({
        "type": "text",
        "text": "*Change status:*",
    })
    components.append({"type": "spacer", "size": "xs"})

    for status_value, label, icon in [
        ("working_example", "Mark as Working", "\U0001f7e2"),
        ("broken_example", "Mark as Broken", "\U0001f534"),
        ("neutral_or_unknown", "Mark as Unknown", "\U00002753"),
    ]:
        if status_value == link.example_status:
            continue
        components.append({
            "type": "button",
            "label": f"{icon} {label}",
            "style": "secondary",
            "id": f"set_status:{status_value}:{link.url}",
            "action": {"type": "submit"},
        })

    components.append({"type": "spacer", "size": "m"})
    components.append({
        "type": "button",
        "label": "Back",
        "style": "secondary",
        "id": "back_to_main",
        "action": {"type": "submit"},
    })

    return {
        "canvas": {
            "content": {"components": components},
            "stored_data": {
                "current_view": "detail",
                "detail_url": link.url,
            },
        }
    }


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


@router.get("/corrections")
async def get_corrections(
    conversation_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    corrections = _correction_store.list_corrections(
        conversation_id=conversation_id,
        limit=limit,
    )
    return {"corrections": corrections, "total": len(corrections)}


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

        # Handle correction detail view
        if clicked.startswith("correct:"):
            url = clicked[len("correct:"):]
            response = _analyze_conversation(conversation_id)
            link = next((l for l in response.links if l.url == url), None)
            if link is None:
                return _error_canvas(f"Link not found: {url}")
            return _build_detail_canvas(link, conversation_id)

        # Handle status change
        if clicked.startswith("set_status:"):
            remainder = clicked[len("set_status:"):]
            sep_idx = remainder.index(":")
            new_status = remainder[:sep_idx]
            url = remainder[sep_idx + 1:]
            admin_id, admin_email = _extract_admin(body)
            response = _analyze_conversation(conversation_id)
            link = next((l for l in response.links if l.url == url), None)
            if link:
                _correction_store.save_correction(
                    conversation_id=conversation_id,
                    message_id=link.message_id,
                    url=url,
                    original_status=link.example_status,
                    corrected_status=new_status,
                    admin_id=admin_id,
                    admin_email=admin_email,
                )
            response = _analyze_conversation(conversation_id)
            filtered = _apply_filters(response, set())
            canvas = _build_canvas(filtered)
            canvas["canvas"]["stored_data"] = {"current_filters": [], "current_view": "main"}
            return canvas

        # Handle back to main
        if clicked == "back_to_main":
            response = _analyze_conversation(conversation_id)
            stored = body.get("stored_data", {})
            active_filters: set[str] = set(stored.get("current_filters", []))
            filtered = _apply_filters(response, active_filters)
            canvas = _build_canvas(filtered, active_filters)
            canvas["canvas"]["stored_data"] = {
                "current_filters": sorted(active_filters),
                "current_view": "main",
            }
            return canvas

        # Handle refresh
        if clicked == "refresh":
            _cache.invalidate(conversation_id)

        # Handle filters (existing logic)
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

        canvas["canvas"]["stored_data"] = {
            "current_filters": sorted(active_filters),
            "current_view": "main",
        }
        return canvas
    except Exception as exc:
        logger.exception("canvas_submit failed")
        return _error_canvas(f"Error: {type(exc).__name__}: {exc}")
