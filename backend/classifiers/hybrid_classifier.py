from __future__ import annotations

from backend.models import ClassificationSignals, ExampleStatus

from backend.classifiers.rule_classifier import RuleClassifier
from backend.classifiers.transformer_classifier import TransformerClassifier


class HybridClassifier:
    def __init__(
        self,
        rule_weight: float = 0.6,
        transformer_weight: float = 0.4,
        confidence_threshold: float = 0.3,
        use_transformer: bool = True,
    ) -> None:
        self._rule_weight = rule_weight
        self._transformer_weight = transformer_weight
        self._confidence_threshold = confidence_threshold
        self._use_transformer = use_transformer

        self._rule = RuleClassifier()
        self._transformer = TransformerClassifier() if use_transformer else None

    def classify(
        self,
        text: str,
        fallback_used: bool = False,
        url_type: str | None = None,
    ) -> tuple[ExampleStatus, float, ClassificationSignals]:
        rule_status, rule_confidence, signals = self._rule.classify(text)

        if not self._use_transformer or self._transformer is None:
            signals.fallback_used = fallback_used
            signals.url_type_match = url_type
            if rule_confidence < self._confidence_threshold:
                return ExampleStatus.NEUTRAL_OR_UNKNOWN, rule_confidence, signals
            return rule_status, rule_confidence, signals

        tx_status, tx_confidence, tx_score = self._transformer.classify(text)
        signals.transformer_score = tx_score

        if rule_status == tx_status:
            combined_confidence = (
                rule_confidence * self._rule_weight
                + tx_confidence * self._transformer_weight
            )
            final_status = rule_status
        else:
            weighted_rule = rule_confidence * self._rule_weight
            weighted_tx = tx_confidence * self._transformer_weight

            # Deterministic rule logic wins when explicit negative phrases are present
            has_explicit_negative = len(signals.negative_phrases) > 0

            if has_explicit_negative:
                final_status = rule_status
                combined_confidence = weighted_rule
            elif weighted_rule >= weighted_tx:
                final_status = rule_status
                combined_confidence = weighted_rule
            else:
                final_status = tx_status
                combined_confidence = weighted_tx

        signals.fallback_used = fallback_used
        signals.url_type_match = url_type

        if combined_confidence < self._confidence_threshold:
            final_status = ExampleStatus.NEUTRAL_OR_UNKNOWN

        return final_status, combined_confidence, signals
