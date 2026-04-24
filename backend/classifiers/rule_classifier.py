from __future__ import annotations

import spacy
from spacy.matcher import PhraseMatcher

from backend.models import ClassificationSignals, ExampleStatus


POSITIVE_PHRASES = [
    "works",
    "working",
    "expected",
    "success",
    "this example works",
    "reproduces correctly",
    "can confirm this works",
    "valid example",
    "successful",
    "functioning",
    "resolved",
    "fixed",
]

NEGATIVE_PHRASES = [
    "broken",
    "not working",
    "doesn't work",
    "fails",
    "failing",
    "issue",
    "error",
    "bug",
    "reproduce",
    "reproduces the issue",
    "timeout",
    "crash",
    "invalid",
    "incorrect",
    "not expected",
    "problem",
    "broken example",
]

UNCERTAINTY_PHRASES = [
    "maybe",
    "seems",
    "I think",
    "possibly",
    "might",
    "could be",
    "not sure",
]

FRAMING_PHRASES = [
    "here is an example",
    "this conversation shows",
    "see this workflow",
    "take a look at",
    "check this",
]

NEGATION_CUES = frozenset({
    "not", "no", "n't", "never", "neither", "without",
    "don't", "doesn't", "didn't", "isn't", "aren't",
    "wasn't", "weren't", "won't", "can't", "couldn't",
    "shouldn't", "wouldn't", "haven't", "hasn't", "hadn't",
})

NEGATION_WINDOW = 3


class RuleClassifier:
    def __init__(self) -> None:
        self._nlp = spacy.load("en_core_web_sm")
        self._matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")

        self._matcher.add("POSITIVE", [self._nlp.make_doc(p) for p in POSITIVE_PHRASES])
        self._matcher.add("NEGATIVE", [self._nlp.make_doc(p) for p in NEGATIVE_PHRASES])
        self._matcher.add("UNCERTAINTY", [self._nlp.make_doc(p) for p in UNCERTAINTY_PHRASES])
        self._matcher.add("FRAMING", [self._nlp.make_doc(p) for p in FRAMING_PHRASES])

    def _has_negation(self, doc: spacy.tokens.Doc, start: int) -> bool:
        window_start = max(0, start - NEGATION_WINDOW)
        for i in range(window_start, start):
            token_lower = doc[i].text.lower()
            if token_lower in NEGATION_CUES:
                return True
        return False

    def classify(self, text: str) -> tuple[ExampleStatus, float, ClassificationSignals]:
        doc = self._nlp(text)
        matches = self._matcher(doc)

        positive_matched: list[str] = []
        negative_matched: list[str] = []
        neutral_matched: list[str] = []
        uncertainty_count = 0

        for match_id, start, end in matches:
            label = self._nlp.vocab.strings[match_id]
            span_text = doc[start:end].text
            negated = self._has_negation(doc, start)

            if label == "POSITIVE":
                if negated:
                    negative_matched.append(span_text)
                else:
                    positive_matched.append(span_text)
            elif label == "NEGATIVE":
                if negated:
                    positive_matched.append(span_text)
                else:
                    negative_matched.append(span_text)
            elif label == "UNCERTAINTY":
                neutral_matched.append(span_text)
                uncertainty_count += 1
            elif label == "FRAMING":
                neutral_matched.append(span_text)

        rule_score = float(len(positive_matched) - len(negative_matched))

        if rule_score > 0:
            status = ExampleStatus.WORKING_EXAMPLE
        elif rule_score < 0:
            status = ExampleStatus.BROKEN_EXAMPLE
        else:
            status = ExampleStatus.NEUTRAL_OR_UNKNOWN

        confidence = min(abs(rule_score) / 3.0, 1.0)
        confidence = max(confidence - (uncertainty_count * 0.3), 0.0)

        signals = ClassificationSignals(
            positive_phrases=positive_matched,
            negative_phrases=negative_matched,
            neutral_phrases=neutral_matched,
            rule_score=rule_score,
        )

        return status, confidence, signals
