from __future__ import annotations

import re

import spacy
from spacy.matcher import PhraseMatcher

from backend.models import AuthorType, ConversationMessage

_PROBLEM_PHRASES = [
    "broken", "not working", "doesn't work", "fails", "failing",
    "issue", "error", "bug", "reproduce", "timeout", "crash",
    "invalid", "incorrect", "not expected", "problem", "broken example",
    "can't", "unable", "wrong", "unexpected", "stuck", "hangs",
    "doesn't trigger", "not triggering", "not firing",
]

_FRAMING_PHRASES = [
    "here is an example", "this conversation shows", "see this workflow",
    "take a look at", "check this", "having trouble", "having an issue",
    "experiencing", "noticed that", "seems like", "appears to be",
    "the issue is", "the problem is", "the bug is",
]

_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"'\)]+")

_MIN_SENTENCE_LEN = 15


class ProblemSummarizer:
    def __init__(self) -> None:
        self._nlp = spacy.load("en_core_web_sm")
        self._matcher = PhraseMatcher(self._nlp.vocab, attr="LOWER")
        self._matcher.add("PROBLEM", [self._nlp.make_doc(p) for p in _PROBLEM_PHRASES])
        self._matcher.add("FRAMING", [self._nlp.make_doc(p) for p in _FRAMING_PHRASES])

    def summarize(self, messages: list[ConversationMessage]) -> str:
        best_score = 0.0
        best_text = ""

        for msg in messages:
            clean = _URL_RE.sub("", msg.body_text).strip()
            if len(clean) < _MIN_SENTENCE_LEN:
                continue

            doc = self._nlp(clean)
            for sent in doc.sents:
                sent_text = sent.text.strip()
                if len(sent_text) < _MIN_SENTENCE_LEN:
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

                if score > best_score:
                    best_score = score
                    best_text = sent_text

        if best_text:
            return best_text[:200] + "..." if len(best_text) > 200 else best_text

        for msg in messages:
            clean = _URL_RE.sub("", msg.body_text).strip()
            if len(clean) >= _MIN_SENTENCE_LEN:
                return clean[:200] + "..." if len(clean) > 200 else clean

        return ""
