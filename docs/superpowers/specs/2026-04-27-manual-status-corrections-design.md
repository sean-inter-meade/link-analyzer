# Manual Status Corrections — Design Spec

## Problem

The link analyzer's hybrid classifier (rule-based NLP + optional transformer) automatically categorizes each URL's example status as `working_example`, `broken_example`, or `neutral_or_unknown`. When it gets the classification wrong, there is no way for a user to correct it, and no mechanism to record these errors for future classifier improvement.

## Goals

1. Let users override the auto-classified example status of any link via the Canvas Kit UI.
2. Record the conversation ID and message part ID that the URL came from, along with who made the correction, so corrections can be reviewed and used to improve the classifier.
3. Show corrections immediately in the UI after they are made.

## Approach: Post-Pipeline Override

Corrections are applied as an overlay after the analysis pipeline runs. The pipeline and classifier remain unchanged. A separate corrections layer checks SQLite for human overrides and patches the results before rendering.

### Why this approach

- Zero changes to the classifier, extractor, or pipeline logic.
- Corrections are cleanly separated — easy to export, review, or roll back.
- Cache stores raw pipeline output; corrections are applied on top each time, so no cache invalidation is needed when a correction is saved.

## Data Model

### SQLite Table: `corrections`

```sql
CREATE TABLE corrections (
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
);
```

- `UNIQUE(conversation_id, url)` — one active correction per URL per conversation. Re-correcting the same link updates the existing row via `INSERT OR REPLACE`.
- `message_id` — the message part the URL was extracted from, for provenance.
- `original_status` — what the classifier produced, for training data.
- `corrected_status` — what the human chose.
- `admin_id` / `admin_email` — extracted from the Canvas Kit submit payload.

Database file: `backend/data/corrections.db`, created on first access with `CREATE TABLE IF NOT EXISTS`.

### Pydantic Model Changes

Add to `ExtractedLink` in `backend/models/classification.py`:

```python
corrected: bool = False
```

This flag indicates whether a link's status was human-corrected vs auto-classified.

### New Service: `CorrectionStore`

File: `backend/services/correction_store.py`

Methods:
- `save_correction(conversation_id, message_id, url, original_status, corrected_status, admin_id, admin_email)` — upserts a correction row.
- `get_corrections(conversation_id) → dict[str, str]` — returns `{url: corrected_status}` for fast lookup.
- `delete_correction(conversation_id, url)` — removes a correction (reverts to auto-classification).

Uses Python's built-in `sqlite3` module. Connection created per call (SQLite handles this efficiently). Table created on `__init__` with `CREATE TABLE IF NOT EXISTS`.

## Pipeline Integration

### `_apply_corrections(response: AnalysisResponse) → AnalysisResponse`

Added to `backend/api/routes.py`. After the pipeline (or cache) produces a response, this function:

1. Fetches corrections for the conversation from `CorrectionStore`.
2. For each link with a correction, overwrites `example_status` and sets `corrected = True`.
3. Re-groups links via `Grouper.group_by_status()` since links may have moved between groups.
4. Returns the patched response.

### Call sites

- `_analyze_conversation()` — after pipeline/cache, before returning.
- `canvas_submit()` — after saving a new correction, re-fetch and apply before rendering.

### Cache interaction

- Cache stores raw pipeline output (no corrections baked in).
- Corrections are overlaid on each read.
- No cache invalidation needed when corrections change.
- "Refresh" button (which invalidates cache and re-runs the pipeline) still shows corrections because they're applied post-cache.

## Canvas Kit UI

### Main view

Existing link rows are unchanged except:
- Each link row becomes clickable (triggers a submit action with `component_id = "correct:<url>"`).
- Corrected links display an `(edited)` marker appended to their text.

### Detail view (status picker)

When a user clicks a link row, the submit handler returns a detail canvas:
- Shows the URL and its current status.
- Three buttons: "Mark as Working", "Mark as Broken", "Mark as Unknown".
- A "Back" button to return to the main view.

Each status button has `component_id = "set_status:<new_status>:<url>"` (status before URL to avoid ambiguity when splitting, since URLs contain colons).

### Admin identity extraction

The admin object is extracted from the submit payload via `body.get("admin", {})`. Expected fields: `admin.id` (string) and `admin.email` (string). Both fall back to `None` if not present — corrections still save without admin identity.

### Correction submit

When the user picks a new status:
1. The handler extracts admin identity as described above.
2. Looks up the link's original auto-classified status from the cached pipeline result.
3. Calls `CorrectionStore.save_correction(...)`.
4. Re-loads the analysis, applies all corrections, re-renders the main canvas.
5. The user sees the link in its new group with the `(edited)` marker.

### Stored data

Canvas Kit `stored_data` gains:
- `current_view`: `"main"` or `"detail"` — determines which screen to render.
- `detail_url`: the URL being corrected (when in detail view).

Existing `current_filters` stored data is preserved.

## Review API

### `GET /corrections`

Returns all stored corrections for classifier improvement review.

Query parameters:
- `conversation_id` (optional) — filter to a specific conversation.
- `limit` (optional, default 100) — pagination cap.

Response:

```json
{
  "corrections": [
    {
      "conversation_id": "12345",
      "message_id": "msg_2",
      "url": "https://app.intercom.com/workflows/123",
      "original_status": "neutral_or_unknown",
      "corrected_status": "broken_example",
      "admin_id": "67890",
      "admin_email": "sean@intercom.io",
      "created_at": "2026-04-27T10:30:00"
    }
  ],
  "total": 1
}
```

## Files Changed

| File | Change |
|---|---|
| `backend/services/correction_store.py` | New — SQLite wrapper service |
| `backend/models/classification.py` | Add `corrected: bool = False` to `ExtractedLink` |
| `backend/api/routes.py` | Add `_apply_corrections()`, detail canvas builder, submit handler routing for `correct:*` and `set_status:*`, `GET /corrections` endpoint |
| `backend/data/` | New directory — SQLite database created at runtime |

## Out of Scope

- Global corrections (corrections are per-conversation only).
- Bulk management API (corrections created/updated only via Canvas Kit).
- Classifier retraining automation (the review endpoint provides data; training is manual).
- URL type corrections (only example status is correctable).
