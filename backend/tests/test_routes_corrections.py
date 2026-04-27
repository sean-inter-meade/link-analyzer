from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
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


class TestCorrectionsEndpoint:
    def test_get_corrections_empty(self, store):
        client = TestClient(app)
        with patch("backend.api.routes._correction_store", store):
            resp = client.get("/corrections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["corrections"] == []
        assert data["total"] == 0

    def test_get_corrections_returns_all(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://example.com/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        client = TestClient(app)
        with patch("backend.api.routes._correction_store", store):
            resp = client.get("/corrections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["corrections"][0]["conversation_id"] == "conv_1"
        assert data["corrections"][0]["corrected_status"] == "working_example"

    def test_get_corrections_filter_by_conversation(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://example.com/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id=None,
            admin_email=None,
        )
        store.save_correction(
            conversation_id="conv_2",
            message_id="msg_2",
            url="https://example.com/2",
            original_status="broken_example",
            corrected_status="neutral_or_unknown",
            admin_id=None,
            admin_email=None,
        )
        client = TestClient(app)
        with patch("backend.api.routes._correction_store", store):
            resp = client.get("/corrections?conversation_id=conv_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["corrections"][0]["conversation_id"] == "conv_1"

    def test_get_corrections_with_limit(self, store):
        for i in range(5):
            store.save_correction(
                conversation_id=f"conv_{i}",
                message_id=f"msg_{i}",
                url=f"https://example.com/{i}",
                original_status="broken_example",
                corrected_status="working_example",
                admin_id=None,
                admin_email=None,
            )
        client = TestClient(app)
        with patch("backend.api.routes._correction_store", store):
            resp = client.get("/corrections?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
