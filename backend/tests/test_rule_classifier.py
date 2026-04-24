from backend.models import ExampleStatus
from backend.classifiers.rule_classifier import RuleClassifier


def test_positive_text(rule_classifier: RuleClassifier) -> None:
    status, _confidence, _signals = rule_classifier.classify("this example works perfectly")
    assert status == ExampleStatus.WORKING_EXAMPLE


def test_negative_text(rule_classifier: RuleClassifier) -> None:
    status, _confidence, _signals = rule_classifier.classify("this workflow is broken and fails")
    assert status == ExampleStatus.BROKEN_EXAMPLE


def test_neutral_text(rule_classifier: RuleClassifier) -> None:
    status, _confidence, _signals = rule_classifier.classify("here is a link to the conversation")
    assert status == ExampleStatus.NEUTRAL_OR_UNKNOWN


def test_negation_flips_negative(rule_classifier: RuleClassifier) -> None:
    status, _confidence, _signals = rule_classifier.classify("this is not broken anymore")
    assert status != ExampleStatus.BROKEN_EXAMPLE


def test_negation_flips_positive(rule_classifier: RuleClassifier) -> None:
    status, _confidence, _signals = rule_classifier.classify("this doesn't work")
    assert status == ExampleStatus.BROKEN_EXAMPLE


def test_uncertainty_reduces_confidence(rule_classifier: RuleClassifier) -> None:
    _, certain_confidence, _ = rule_classifier.classify("this works")
    _, uncertain_confidence, _ = rule_classifier.classify("maybe this works")
    assert uncertain_confidence < certain_confidence


def test_mixed_signals(rule_classifier: RuleClassifier) -> None:
    _status, _confidence, signals = rule_classifier.classify("this works but that one fails")
    assert len(signals.positive_phrases) > 0
    assert len(signals.negative_phrases) > 0
