from __future__ import annotations

from datetime import datetime

import pytest

from backend.models import (
    AnalysisResponse,
    AnalysisSummary,
    ClassificationSignals,
    ExtractedLink,
    LinkGroup,
)
from backend.services.correction_store import CorrectionStore
from backend.services.grouper import Grouper


def _make_link(url: str, message_id: str, status: str) -> ExtractedLink:
    return ExtractedLink(
        url=url,
        message_id=message_id,
        message_author_type="user",
        message_created_at=datetime(2024, 1, 1),
        surrounding_text="some text",
        selected_context_text="some text",
        selected_context_message_id=message_id,
        selected_context_author_type="user",
        selected_context_reason="current_message_has_meaningful_text",
        url_type="workflow",
        example_status=status,
        confidence=0.8,
        signals=ClassificationSignals(),
    )


def _make_response(links: list[ExtractedLink]) -> AnalysisResponse:
    grouper = Grouper()
    summary, groups = grouper.group_by_status(links)
    return AnalysisResponse(
        conversation_id="conv_1",
        summary=summary,
        links=links,
        groups=groups,
    )


@pytest.fixture
def store(tmp_path):
    return CorrectionStore(db_path=str(tmp_path / "test.db"))


class TestApplyCorrections:
    def test_no_corrections_returns_unchanged(self, store):
        from backend.api.routes import _apply_corrections

        link = _make_link("https://example.com/1", "msg_1", "broken_example")
        response = _make_response([link])
        result = _apply_corrections(response, store)
        assert result.links[0].example_status == "broken_example"
        assert result.links[0].corrected is False

    def test_correction_overrides_status(self, store):
        from backend.api.routes import _apply_corrections

        link = _make_link("https://example.com/1", "msg_1", "broken_example")
        response = _make_response([link])

        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://example.com/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )

        result = _apply_corrections(response, store)
        assert result.links[0].example_status == "working_example"
        assert result.links[0].corrected is True

    def test_correction_regroups_links(self, store):
        from backend.api.routes import _apply_corrections

        link1 = _make_link("https://example.com/1", "msg_1", "broken_example")
        link2 = _make_link("https://example.com/2", "msg_2", "broken_example")
        response = _make_response([link1, link2])

        assert response.summary.broken_count == 2
        assert response.summary.working_count == 0

        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://example.com/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id=None,
            admin_email=None,
        )

        result = _apply_corrections(response, store)
        assert result.summary.broken_count == 1
        assert result.summary.working_count == 1

    def test_correction_only_affects_matching_url(self, store):
        from backend.api.routes import _apply_corrections

        link1 = _make_link("https://example.com/1", "msg_1", "broken_example")
        link2 = _make_link("https://example.com/2", "msg_2", "broken_example")
        response = _make_response([link1, link2])

        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://example.com/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id=None,
            admin_email=None,
        )

        result = _apply_corrections(response, store)
        assert result.links[0].example_status == "working_example"
        assert result.links[0].corrected is True
        assert result.links[1].example_status == "broken_example"
        assert result.links[1].corrected is False
