# Manual Status Corrections — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users override auto-classified example statuses via Canvas Kit, persisting corrections in SQLite with full provenance for classifier improvement.

**Architecture:** Post-pipeline override. The analysis pipeline runs unchanged; a corrections layer overlays human overrides from SQLite before rendering. Canvas Kit uses a two-screen flow (main list → detail status picker).

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite (stdlib `sqlite3`), pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/correction_store.py` | Create | SQLite wrapper: save, get, delete corrections |
| `backend/tests/test_correction_store.py` | Create | Unit tests for CorrectionStore |
| `backend/models/classification.py` | Modify (line 69) | Add `corrected: bool = False` to ExtractedLink |
| `backend/api/routes.py` | Modify | Add `_apply_corrections()`, `_build_detail_canvas()`, update `canvas_submit`, add `GET /corrections` |
| `backend/tests/test_routes_corrections.py` | Create | Integration tests for correction flow and review API |

---

### Task 1: CorrectionStore — SQLite Service

**Files:**
- Create: `backend/services/correction_store.py`
- Create: `backend/tests/test_correction_store.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_correction_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_correction_store.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'backend.services.correction_store'`

- [ ] **Step 3: Write the CorrectionStore implementation**

Create `backend/services/correction_store.py`:

```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


_DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "corrections.db"
)


class CorrectionStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    original_status TEXT NOT NULL,
                    corrected_status TEXT NOT NULL,
                    admin_id TEXT,
                    admin_email TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(conversation_id, url)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save_correction(
        self,
        conversation_id: str,
        message_id: str,
        url: str,
        original_status: str,
        corrected_status: str,
        admin_id: Optional[str],
        admin_email: Optional[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO corrections
                    (conversation_id, message_id, url, original_status,
                     corrected_status, admin_id, admin_email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id, url) DO UPDATE SET
                    message_id = excluded.message_id,
                    corrected_status = excluded.corrected_status,
                    original_status = excluded.original_status,
                    admin_id = excluded.admin_id,
                    admin_email = excluded.admin_email,
                    created_at = datetime('now')
                """,
                (
                    conversation_id,
                    message_id,
                    url,
                    original_status,
                    corrected_status,
                    admin_id,
                    admin_email,
                ),
            )

    def get_corrections(self, conversation_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, corrected_status FROM corrections WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        return {url: status for url, status in rows}

    def delete_correction(self, conversation_id: str, url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM corrections WHERE conversation_id = ? AND url = ?",
                (conversation_id, url),
            )

    def list_corrections(
        self,
        conversation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._connect() as conn:
            if conversation_id:
                rows = conn.execute(
                    """
                    SELECT conversation_id, message_id, url, original_status,
                           corrected_status, admin_id, admin_email, created_at
                    FROM corrections
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT conversation_id, message_id, url, original_status,
                           corrected_status, admin_id, admin_email, created_at
                    FROM corrections
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        columns = [
            "conversation_id", "message_id", "url", "original_status",
            "corrected_status", "admin_id", "admin_email", "created_at",
        ]
        return [dict(zip(columns, row)) for row in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_correction_store.py -v`

Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add backend/services/correction_store.py backend/tests/test_correction_store.py
git commit -m "feat: add CorrectionStore SQLite service with tests"
```

---

### Task 2: Add `corrected` Flag to ExtractedLink

**Files:**
- Modify: `backend/models/classification.py:55-69`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_correction_model.py`:

```python
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
```

- [ ] **Step 2: Run test to verify first test passes and second fails**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_correction_model.py -v`

Expected: `test_extracted_link_corrected_defaults_false` may pass (Pydantic ignores unknown fields by default) or both fail. Either way, the `corrected=True` test should fail with a validation error since the field doesn't exist yet.

- [ ] **Step 3: Add the `corrected` field to ExtractedLink**

In `backend/models/classification.py`, add the field after `signals` (line 69):

```python
# Change the ExtractedLink class — add `corrected` after the `signals` field:
class ExtractedLink(BaseModel):
    url: str
    message_id: str
    message_author_type: str
    message_created_at: datetime
    anchor_text: Optional[str] = None
    surrounding_text: str
    selected_context_text: str
    selected_context_message_id: str
    selected_context_author_type: str
    selected_context_reason: str
    url_type: str
    example_status: str
    confidence: float
    signals: ClassificationSignals
    corrected: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_correction_model.py -v`

Expected: Both tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/ -v`

Expected: All existing tests still PASS (the new field has a default, so no existing code breaks)

- [ ] **Step 6: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add backend/models/classification.py backend/tests/test_correction_model.py
git commit -m "feat: add corrected flag to ExtractedLink model"
```

---

### Task 3: Pipeline Integration — `_apply_corrections()`

**Files:**
- Modify: `backend/api/routes.py:27` (add import)
- Modify: `backend/api/routes.py:39` (add `_correction_store` singleton)
- Modify: `backend/api/routes.py:186-196` (update `_analyze_conversation`)
- Create: `backend/tests/test_routes_corrections.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_routes_corrections.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_routes_corrections.py -v`

Expected: FAIL with `ImportError: cannot import name '_apply_corrections' from 'backend.api.routes'`

- [ ] **Step 3: Implement `_apply_corrections()` in routes.py**

Add the import at the top of `backend/api/routes.py` (after line 27, the existing imports):

```python
from backend.services.correction_store import CorrectionStore
```

Add the singleton after the existing singletons (after `_provider` on line 39):

```python
_correction_store = CorrectionStore()
```

Add the `_apply_corrections` function (before `_analyze_conversation`, around line 186):

```python
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
```

Update `_analyze_conversation` to call `_apply_corrections` before returning:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_routes_corrections.py -v`

Expected: All 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add backend/api/routes.py backend/tests/test_routes_corrections.py
git commit -m "feat: add _apply_corrections post-pipeline overlay"
```

---

### Task 4: Canvas Kit — Detail View & Correction Submit

**Files:**
- Modify: `backend/api/routes.py` (add `_build_detail_canvas`, update `canvas_submit`, update `_build_canvas`)

- [ ] **Step 1: Add `_build_detail_canvas` to routes.py**

Add this function after `_build_canvas` (around line 408):

```python
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
```

- [ ] **Step 2: Update `_build_canvas` to make link rows clickable**

In `_build_canvas`, replace the link text component for intercom links (the block starting at line 367):

Find this block inside the `for link in group.items:` loop:

```python
                components.append({
                    "type": "text",
                    "text": f"{type_icon} [{item_id}]({admin_url}) [app]({link_url}) ({confidence_pct})",
                })
```

Replace with:

```python
                edited_marker = " ✏️" if link.corrected else ""
                components.append({
                    "type": "button",
                    "label": f"{type_icon} {type_label} {item_id} ({confidence_pct}){edited_marker}",
                    "style": "link",
                    "id": f"correct:{link_url}",
                    "action": {"type": "submit"},
                })
```

Note: Canvas Kit `"style": "link"` renders the button as a text-like link. If that's not supported, use `"secondary"` instead. The `type_label` variable is already computed on line 364.

- [ ] **Step 3: Extract admin identity helper**

Add this helper function near the top of routes.py (after `_get_provider`):

```python
def _extract_admin(body: dict[str, Any]) -> tuple[str | None, str | None]:
    admin = body.get("admin") or {}
    admin_id = str(admin["id"]) if "id" in admin else None
    admin_email = admin.get("email")
    return admin_id, admin_email
```

- [ ] **Step 4: Update `canvas_submit` to handle correction flow**

Replace the entire `canvas_submit` function with:

```python
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
        # Format: "set_status:<status>:<url>" — status before URL
        # because URLs contain colons and we split from the left
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
```

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add backend/api/routes.py
git commit -m "feat: add Canvas Kit detail view and correction submit handling"
```

---

### Task 5: Review API — `GET /corrections`

**Files:**
- Modify: `backend/api/routes.py` (add endpoint)
- Modify: `backend/tests/test_routes_corrections.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_routes_corrections.py`:

```python
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app import app


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_routes_corrections.py::TestCorrectionsEndpoint -v`

Expected: FAIL with 404 (endpoint doesn't exist yet)

- [ ] **Step 3: Add the GET /corrections endpoint**

Add to `backend/api/routes.py`, after the `canvas_submit` function:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/test_routes_corrections.py -v`

Expected: All tests PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add backend/api/routes.py backend/tests/test_routes_corrections.py
git commit -m "feat: add GET /corrections review endpoint"
```

---

### Task 6: Add `corrections.db` to `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the database file to .gitignore**

Append to `.gitignore`:

```
# SQLite correction database (created at runtime)
backend/data/*.db
```

- [ ] **Step 2: Commit**

```bash
cd /Users/seanmeade/src/link-analyzer
git add .gitignore
git commit -m "chore: gitignore SQLite database files"
```

---

### Task 7: End-to-End Manual Verification

- [ ] **Step 1: Start the dev server**

Run: `cd /Users/seanmeade/src/link-analyzer && uvicorn backend.app:app --reload`

Verify: Server starts without errors, logs show "Link Analyzer started"

- [ ] **Step 2: Test the corrections API**

In a separate terminal:

```bash
# Should return empty corrections
curl -s http://localhost:8000/corrections | python -m json.tool
```

Expected: `{"corrections": [], "total": 0}`

- [ ] **Step 3: Run full test suite one final time**

Run: `cd /Users/seanmeade/src/link-analyzer && python -m pytest backend/tests/ -v`

Expected: All tests PASS
