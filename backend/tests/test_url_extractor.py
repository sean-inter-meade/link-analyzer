from datetime import datetime, timezone

from backend.models import ConversationMessage, AuthorType
from backend.services.url_extractor import UrlExtractor


def test_extracts_url_from_message(
    url_extractor: UrlExtractor,
    user_reports_broken_workflow: list[ConversationMessage],
) -> None:
    results = url_extractor.extract(user_reports_broken_workflow)
    urls = [r["url"] for r in results]
    assert "https://app.intercom.com/workflows/123" in urls
    workflow_entry = next(r for r in results if "workflows/123" in r["url"])
    assert workflow_entry["message_id"] == "msg2"


def test_detects_bare_url(
    url_extractor: UrlExtractor,
    bare_url_with_broken_previous: list[ConversationMessage],
) -> None:
    results = url_extractor.extract(bare_url_with_broken_previous)
    bare_entry = next(r for r in results if "conversations/789" in r["url"])
    assert bare_entry["is_bare_url"] is True


def test_multiple_urls_in_one_message(
    url_extractor: UrlExtractor,
    multiple_urls_mixed: list[ConversationMessage],
) -> None:
    results = url_extractor.extract(multiple_urls_mixed)
    urls = [r["url"] for r in results]
    assert len(urls) == 3
    assert any("github.com" in u for u in urls)
    assert any("workflows/999" in u for u in urls)
    assert any("loom.com" in u for u in urls)


def test_no_urls_in_plain_text(url_extractor: UrlExtractor) -> None:
    messages = [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text="There are no links in this message at all",
            created_at=datetime(2024, 1, 15, 0, 1, tzinfo=timezone.utc),
            conversation_id="conv_test",
        ),
    ]
    results = url_extractor.extract(messages)
    assert results == []


def test_surrounding_text_captured(
    url_extractor: UrlExtractor,
    user_reports_broken_workflow: list[ConversationMessage],
) -> None:
    results = url_extractor.extract(user_reports_broken_workflow)
    workflow_entry = next(r for r in results if "workflows/123" in r["url"])
    assert len(workflow_entry["surrounding_text"]) > 0
    assert "doesn't work" in workflow_entry["surrounding_text"] or "failing" in workflow_entry["surrounding_text"]
