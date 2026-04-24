# Link Analyzer -- Intercom Canvas Kit App

Link Analyzer is a FastAPI backend that extracts URLs from Intercom conversation transcripts, classifies each link as a working example, broken example, or neutral/unknown, and renders the results via the Intercom Canvas Kit. It combines rule-based NLP with an optional zero-shot transformer model to produce high-confidence classifications.

## Architecture

The analysis pipeline is modular and sequential:

1. **Conversation Ingestion** -- Messages are received via API or fetched from Intercom.
2. **URL Extraction** -- All URLs are identified with surrounding text and bare-URL detection.
3. **URL Categorization** -- Each URL is mapped to a type (conversation, workflow, custom_action, article, help_center, loom, github, other) using configurable pattern rules.
4. **Context Resolution** -- The most informative text for each URL is selected, falling back to previous messages when the current message is a bare URL or lacks meaningful content.
5. **Hybrid Classification** -- A rule-based spaCy classifier (with negation handling) is combined with an optional zero-shot transformer to determine whether the link is a working example, broken example, or neutral/unknown.
6. **Grouping** -- Links are grouped by classification status with summary counts.
7. **Canvas Kit Rendering** -- Results are formatted as an Intercom Canvas Kit payload for display in the Intercom inbox.

## Project Structure

```
link-analyzer/
  backend/
    app.py
    api/
      routes.py
    classifiers/
      rule_classifier.py
      transformer_classifier.py
      hybrid_classifier.py
    config/
      url_patterns.yaml
    models/
      conversation.py
      classification.py
    services/
      url_extractor.py
      url_categorizer.py
      context_resolver.py
      conversation_provider.py
      grouper.py
    tests/
      conftest.py
      fixtures/
        sample_conversations.py
      test_url_extractor.py
      test_url_categorizer.py
      test_context_resolver.py
      test_rule_classifier.py
      test_hybrid_classifier.py
  frontend/
    canvas_app.json
  requirements.txt
  pyproject.toml
  README.md
```

## Setup

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn backend.app:app --reload
```

The server starts on `http://localhost:8000` by default.

## API Endpoints

### GET /health

Health check.

```json
{"status": "ok"}
```

### POST /analyze-conversation

Analyze all links in a conversation by ID (fetched via the conversation provider).

**Request:**

```json
{"conversation_id": "12345"}
```

**Response:**

```json
{
  "conversation_id": "12345",
  "summary": {"working_count": 1, "broken_count": 2, "unknown_count": 0},
  "links": [
    {
      "url": "https://app.intercom.com/workflows/123",
      "message_id": "msg_2",
      "message_author_type": "user",
      "message_created_at": "2024-01-15T00:02:00Z",
      "surrounding_text": "This workflow doesn't work at all - it keeps failing",
      "selected_context_text": "This workflow doesn't work at all - it keeps failing with a timeout",
      "selected_context_reason": "current_message_has_meaningful_text",
      "url_type": "workflow",
      "example_status": "broken_example",
      "confidence": 0.67,
      "signals": {
        "positive_phrases": [],
        "negative_phrases": ["doesn't work", "failing"],
        "rule_score": -2.0
      }
    }
  ],
  "groups": [
    {"example_status": "broken_example", "items": ["..."]}
  ]
}
```

### POST /analyze-preview

Analyze a list of messages directly (no conversation fetch required).

**Request:**

```json
{
  "messages": [
    {
      "id": "msg1",
      "author_type": "user",
      "body_text": "This is broken https://app.intercom.com/workflows/1",
      "created_at": "2024-01-15T00:01:00Z",
      "conversation_id": "preview_1"
    }
  ]
}
```

**Response:** Same structure as `/analyze-conversation`.

### POST /canvas/initialize

Intercom Canvas Kit initialization webhook. Receives the conversation context from Intercom and returns a Canvas Kit payload with the analysis results.

**Request** (sent by Intercom):

```json
{"conversation_id": "12345"}
```

**Response:** Canvas Kit component tree.

### POST /canvas/submit

Intercom Canvas Kit submit handler for interactive actions (filters, re-analysis).

## Configuration

URL categorization patterns are defined in `backend/config/url_patterns.yaml`. Each rule specifies hostname substrings and/or path substrings to match against. Rules are evaluated top-to-bottom; the first match wins. The final rule is a catch-all that maps unrecognized URLs to `other`.

To add a new URL type, append a rule before the catch-all:

```yaml
- url_type: my_new_type
  hostnames:
    - my-service.example.com
  paths:
    - /my-path/
  notes: Description of this URL type
```

## Classification Pipeline

The hybrid classifier combines two strategies:

**Rule-based (spaCy):** A PhraseMatcher detects positive phrases ("works", "can confirm this works"), negative phrases ("broken", "fails", "timeout"), uncertainty markers ("maybe", "possibly"), and framing phrases ("here is an example"). A negation detector checks the 3-token window before each match -- "not broken" flips a negative match to positive. The rule score is `positive_count - negative_count`, and confidence scales with the absolute score, reduced by uncertainty markers.

**Transformer (optional):** A zero-shot classification model (`facebook/bart-large-mnli`) scores the text against candidate labels. Disabled by default for speed; enable by passing `use_transformer=True` to `HybridClassifier`.

When both are active, the final classification uses weighted scores (default 60% rule, 40% transformer). If the rule classifier detects explicit negative phrases, it wins regardless of transformer output. Below the confidence threshold (default 0.3), the result falls back to `neutral_or_unknown`.

**Context resolution** selects the best text to classify for each URL. If the URL's message has meaningful surrounding text, that is used. If the message is a bare URL or has minimal text, the resolver falls back to the previous message in the conversation. Admin messages referencing diagnostic phrases ("try this", "this works") are recognized as contextually relevant.

## Canvas Kit Integration

To register the app in the Intercom Developer Hub:

1. Create a new app at https://developers.intercom.com.
2. Enable the Canvas Kit feature.
3. Set the **Initialize URL** to `https://<your-domain>/canvas/initialize`.
4. Set the **Submit URL** to `https://<your-domain>/canvas/submit`.
5. Install the app on your Intercom workspace.

When a teammate opens a conversation in the inbox, Intercom sends the conversation context to your initialize endpoint, and the Canvas Kit payload is rendered in the app panel.

## Testing

```bash
pytest backend/tests/
```

Tests use `HybridClassifier(use_transformer=False)` so they run quickly without downloading the transformer model.

## TODO -- Integration Points

- [ ] Wire up actual Intercom API conversation fetch in ConversationProvider
- [ ] Add Intercom API authentication (OAuth or API key)
- [ ] Enable transformer model loading for production (currently rule-only by default)
- [ ] Add caching layer for repeated conversation analyses
- [ ] Implement Canvas Kit submit handler for filter actions
- [ ] Add rate limiting
- [ ] Deploy behind HTTPS for Intercom webhook requirements
- [ ] Fine-tune transformer on internal labeled examples
- [ ] Add per-workspace URL pattern overrides

## Extending

**Adding a new URL type:** Edit `backend/config/url_patterns.yaml` and insert a new rule before the catch-all. Add the corresponding value to `UrlType` in `backend/models/classification.py`.

**Adding classification phrases:** Edit the phrase lists in `backend/classifiers/rule_classifier.py`. Positive phrases push toward `WORKING_EXAMPLE`, negative phrases push toward `BROKEN_EXAMPLE`. The negation detector will automatically handle negated forms.
