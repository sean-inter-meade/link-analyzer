from __future__ import annotations

from datetime import datetime

from backend.models import ExtractedLink, ClassificationSignals


def test_extracted_link_corrected_defaults_false():
    link = ExtractedLink(
        url="https://example.com",
        message_id="msg_1",
        message_author_type="user",
        message_created_at=datetime(2024, 1, 1),
        surrounding_text="some text",
        selected_context_text="some text",
        selected_context_message_id="msg_1",
        selected_context_author_type="user",
        selected_context_reason="current_message_has_meaningful_text",
        url_type="workflow",
        example_status="broken_example",
        confidence=0.8,
        signals=ClassificationSignals(),
    )
    assert link.corrected is False


def test_extracted_link_corrected_can_be_set_true():
    link = ExtractedLink(
        url="https://example.com",
        message_id="msg_1",
        message_author_type="user",
        message_created_at=datetime(2024, 1, 1),
        surrounding_text="some text",
        selected_context_text="some text",
        selected_context_message_id="msg_1",
        selected_context_author_type="user",
        selected_context_reason="current_message_has_meaningful_text",
        url_type="workflow",
        example_status="broken_example",
        confidence=0.8,
        signals=ClassificationSignals(),
        corrected=True,
    )
    assert link.corrected is True
