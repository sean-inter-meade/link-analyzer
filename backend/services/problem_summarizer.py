from __future__ import annotations

import spacy
from spacy.matcher import PhraseMatcher

from backend.models import AuthorType, ConversationMessage

_PROBLEM_PHRASES = [
    "broken", "not working", "doesn't work", "fails", "failing",
    "issue", "error", "bug", "reproduce", "timeout", "crash",
    "invalid", "incorrect", "not expected", "problem", "broken example",
    "can't", "unable", "wrong", "unexpected", "stuck", "hangs",
]

_FRAMING_PHRASES = [
    "here is an example", "this conversation shows", "see this workflow",
    "take a look at", "check this", "having trouble", "having an issue",
    "experiencing", "noticed that", "seems like", "appears to be",
]

_REPORTER_TYPES = {AuthorType.USER, AuthorType.LEAD}


class ProblemSummarizer:
    def __init__(self) -> None:
        self._nlp = spacy.load("en_core_web_sm")
        self._matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
        self._matcher.add("PROBLEM", [self._nlp.make_doc(p) for p in _PROBLEM_PHRASES])
        self._matcher.add("FRAMING", [self._nlp.make_doc(p) for p in _FRAMING_PHRASES])

    def summarize(self, messages: list[ConversationMessage], max_sentences: int = 2) -> str:
        reporter_text = " ".join(
            m.body_text for m in messages if m.author_type in _REPORTER_TYPES
        )

        if not reporter_text.strip():
            return ""

        doc = self._nlp(reporter_text)
        scored: list[tuple[float, str]] = []

        for sent in doc.sents:
            sent_text = sent.text.strip()
            if len(sent_text) < 10:
                continue

            sent_doc = sent.as_doc()
            matches = self._matcher(sent_doc)

            score = 0.0
            for match_id, _, _ in matches:
                label = self._nlp.vocab.strings[match_id]
                if label == "PROBLEM":
                    score += 2.0
                elif label == "FRAMING":
                    score += 1.0

            # Boost earlier sentences slightly — problem statements tend to come first
            position_bonus = 0.5 if len(scored) < 3 else 0.0
            score += position_bonus

            if score > 0:
                scored.append((score, sent_text))

        if not scored:
            first_reporter = next(
                (m for m in messages if m.author_type in _REPORTER_TYPES), None
            )
            if first_reporter:
                text = first_reporter.body_text.strip()
                return text[:200] + "..." if len(text) > 200 else text
            return ""

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_sentences]
        return " ".join(text for _, text in top)
