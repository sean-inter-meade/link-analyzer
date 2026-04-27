from __future__ import annotations

import os
import tempfile

import pytest

from backend.services.correction_store import CorrectionStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_corrections.db")
    return CorrectionStore(db_path=db_path)


class TestSaveAndGet:
    def test_save_correction_and_retrieve(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_2",
            url="https://app.intercom.com/workflows/123",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        corrections = store.get_corrections("conv_1")
        assert corrections == {
            "https://app.intercom.com/workflows/123": "broken_example"
        }

    def test_get_corrections_empty(self, store):
        corrections = store.get_corrections("nonexistent")
        assert corrections == {}

    def test_save_multiple_urls_same_conversation(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="broken_example",
            corrected_status="working_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_2",
            url="https://app.intercom.com/workflows/2",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        corrections = store.get_corrections("conv_1")
        assert len(corrections) == 2
        assert corrections["https://app.intercom.com/workflows/1"] == "working_example"
        assert corrections["https://app.intercom.com/workflows/2"] == "broken_example"

    def test_upsert_overwrites_existing(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="working_example",
            admin_id="admin_2",
            admin_email="other@intercom.io",
        )
        corrections = store.get_corrections("conv_1")
        assert corrections["https://app.intercom.com/workflows/1"] == "working_example"

    def test_corrections_scoped_per_conversation(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        assert store.get_corrections("conv_2") == {}


class TestDelete:
    def test_delete_correction(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        store.delete_correction("conv_1", "https://app.intercom.com/workflows/1")
        assert store.get_corrections("conv_1") == {}

    def test_delete_nonexistent_is_noop(self, store):
        store.delete_correction("conv_1", "https://example.com")


class TestListAll:
    def test_list_all_corrections(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        store.save_correction(
            conversation_id="conv_2",
            message_id="msg_5",
            url="https://app.intercom.com/workflows/9",
            original_status="working_example",
            corrected_status="neutral_or_unknown",
            admin_id="admin_2",
            admin_email="other@intercom.io",
        )
        results = store.list_corrections()
        assert len(results) == 2
        assert results[0]["conversation_id"] == "conv_1"
        assert results[0]["message_id"] == "msg_1"
        assert results[0]["url"] == "https://app.intercom.com/workflows/1"
        assert results[0]["original_status"] == "neutral_or_unknown"
        assert results[0]["corrected_status"] == "broken_example"
        assert results[0]["admin_id"] == "admin_1"
        assert results[0]["admin_email"] == "sean@intercom.io"
        assert "created_at" in results[0]

    def test_list_corrections_filtered_by_conversation(self, store):
        store.save_correction(
            conversation_id="conv_1",
            message_id="msg_1",
            url="https://app.intercom.com/workflows/1",
            original_status="neutral_or_unknown",
            corrected_status="broken_example",
            admin_id="admin_1",
            admin_email="sean@intercom.io",
        )
        store.save_correction(
            conversation_id="conv_2",
            message_id="msg_5",
            url="https://app.intercom.com/workflows/9",
            original_status="working_example",
            corrected_status="neutral_or_unknown",
            admin_id=None,
            admin_email=None,
        )
        results = store.list_corrections(conversation_id="conv_1")
        assert len(results) == 1
        assert results[0]["conversation_id"] == "conv_1"

    def test_list_corrections_with_limit(self, store):
        for i in range(5):
            store.save_correction(
                conversation_id=f"conv_{i}",
                message_id=f"msg_{i}",
                url=f"https://example.com/{i}",
                original_status="neutral_or_unknown",
                corrected_status="broken_example",
                admin_id=None,
                admin_email=None,
            )
        results = store.list_corrections(limit=3)
        assert len(results) == 3
