from backend.models import ExampleStatus
from backend.classifiers.hybrid_classifier import HybridClassifier


def test_clear_broken(hybrid_classifier: HybridClassifier) -> None:
    status, _confidence, _signals = hybrid_classifier.classify(
        "this is completely broken and fails every time"
    )
    assert status == ExampleStatus.BROKEN_EXAMPLE


def test_clear_working(hybrid_classifier: HybridClassifier) -> None:
    status, _confidence, _signals = hybrid_classifier.classify(
        "can confirm this works as expected"
    )
    assert status == ExampleStatus.WORKING_EXAMPLE


def test_neutral_below_threshold(hybrid_classifier: HybridClassifier) -> None:
    status, _confidence, _signals = hybrid_classifier.classify("")
    assert status == ExampleStatus.NEUTRAL_OR_UNKNOWN


def test_fallback_flag_set(hybrid_classifier: HybridClassifier) -> None:
    _status, _confidence, signals = hybrid_classifier.classify(
        "some context text here",
        fallback_used=True,
    )
    assert signals.fallback_used is True


def test_url_type_stored(hybrid_classifier: HybridClassifier) -> None:
    _status, _confidence, signals = hybrid_classifier.classify(
        "this workflow is broken",
        url_type="workflow",
    )
    assert signals.url_type_match == "workflow"
