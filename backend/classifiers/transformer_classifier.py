from __future__ import annotations

import logging
from typing import Any

from backend.models import ExampleStatus

logger = logging.getLogger(__name__)

LABEL_TO_STATUS = {
    "working example": ExampleStatus.WORKING_EXAMPLE,
    "broken example": ExampleStatus.BROKEN_EXAMPLE,
    "neutral or unknown": ExampleStatus.NEUTRAL_OR_UNKNOWN,
}

CANDIDATE_LABELS = list(LABEL_TO_STATUS.keys())

MIN_TEXT_LENGTH = 5


class TransformerClassifier:
    _loaded: bool = False
    _pipeline: Any = None

    def __init__(self) -> None:
        pass

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._pipeline is not None

        self._loaded = True
        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                device=-1,
            )
        except Exception:
            logger.exception("Failed to load transformer model")
            self._pipeline = None

        return self._pipeline is not None

    def classify(self, text: str) -> tuple[ExampleStatus, float, float]:
        if not text or len(text.strip()) < MIN_TEXT_LENGTH:
            return ExampleStatus.NEUTRAL_OR_UNKNOWN, 0.0, 0.0

        if not self._ensure_loaded():
            return ExampleStatus.NEUTRAL_OR_UNKNOWN, 0.0, 0.0

        try:
            result = self._pipeline(text, candidate_labels=CANDIDATE_LABELS)
        except Exception:
            logger.exception("Transformer classification failed")
            return ExampleStatus.NEUTRAL_OR_UNKNOWN, 0.0, 0.0

        top_label: str = result["labels"][0]
        top_score: float = result["scores"][0]
        status = LABEL_TO_STATUS.get(top_label, ExampleStatus.NEUTRAL_OR_UNKNOWN)

        return status, top_score, top_score
