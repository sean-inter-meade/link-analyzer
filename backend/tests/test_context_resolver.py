from backend.models import ConversationMessage, ContextReason
from backend.services.url_extractor import UrlExtractor
from backend.services.context_resolver import ContextResolver


def test_user_message_with_meaningful_text(
    url_extractor: UrlExtractor,
    context_resolver: ContextResolver,
    user_reports_broken_workflow: list[ConversationMessage],
) -> None:
    extracted = url_extractor.extract(user_reports_broken_workflow)
    workflow_url = next(e for e in extracted if "workflows/123" in e["url"])
    result = context_resolver.resolve(workflow_url, user_reports_broken_workflow)
    assert result["selected_context_reason"] == ContextReason.CURRENT_MESSAGE_HAS_MEANINGFUL_TEXT.value
    assert result["selected_context_message_id"] == "msg2"


def test_bare_url_falls_back_to_previous(
    url_extractor: UrlExtractor,
    context_resolver: ContextResolver,
    bare_url_with_broken_previous: list[ConversationMessage],
) -> None:
    extracted = url_extractor.extract(bare_url_with_broken_previous)
    conv_url = next(e for e in extracted if "conversations/789" in e["url"])
    result = context_resolver.resolve(conv_url, bare_url_with_broken_previous)
    assert result["selected_context_reason"] == ContextReason.BARE_URL_FALLBACK_TO_PREVIOUS.value
    assert result["selected_context_message_id"] == "msg1"


def test_admin_references_link(
    url_extractor: UrlExtractor,
    context_resolver: ContextResolver,
    admin_confirms_working: list[ConversationMessage],
) -> None:
    extracted = url_extractor.extract(admin_confirms_working)
    article_url = next(e for e in extracted if "articles/100" in e["url"])
    result = context_resolver.resolve(article_url, admin_confirms_working)
    assert result["selected_context_reason"] == ContextReason.ADMIN_MESSAGE_REFERENCES_LINK.value
    assert result["selected_context_message_id"] == "msg2"


def test_neutral_uses_previous(
    url_extractor: UrlExtractor,
    context_resolver: ContextResolver,
    neutral_with_informative_previous: list[ConversationMessage],
) -> None:
    extracted = url_extractor.extract(neutral_with_informative_previous)
    conv_url = next(e for e in extracted if "conversations/555" in e["url"])
    result = context_resolver.resolve(conv_url, neutral_with_informative_previous)
    valid_reasons = {
        ContextReason.PREVIOUS_MESSAGE_USED_DUE_TO_NEUTRAL.value,
        ContextReason.BARE_URL_FALLBACK_TO_PREVIOUS.value,
    }
    assert result["selected_context_reason"] in valid_reasons
    assert result["selected_context_message_id"] == "msg1"
