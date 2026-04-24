import pytest

from backend.models import ConversationMessage
from backend.services.url_extractor import UrlExtractor
from backend.services.url_categorizer import UrlCategorizer
from backend.services.context_resolver import ContextResolver
from backend.classifiers.rule_classifier import RuleClassifier
from backend.classifiers.hybrid_classifier import HybridClassifier
from backend.tests.fixtures.sample_conversations import (
    fixture_user_reports_broken_workflow,
    fixture_admin_sends_url_after_intro,
    fixture_bare_url_with_broken_previous,
    fixture_admin_confirms_working,
    fixture_multiple_urls_mixed,
    fixture_neutral_with_informative_previous,
)


@pytest.fixture
def user_reports_broken_workflow() -> list[ConversationMessage]:
    return fixture_user_reports_broken_workflow()


@pytest.fixture
def admin_sends_url_after_intro() -> list[ConversationMessage]:
    return fixture_admin_sends_url_after_intro()


@pytest.fixture
def bare_url_with_broken_previous() -> list[ConversationMessage]:
    return fixture_bare_url_with_broken_previous()


@pytest.fixture
def admin_confirms_working() -> list[ConversationMessage]:
    return fixture_admin_confirms_working()


@pytest.fixture
def multiple_urls_mixed() -> list[ConversationMessage]:
    return fixture_multiple_urls_mixed()


@pytest.fixture
def neutral_with_informative_previous() -> list[ConversationMessage]:
    return fixture_neutral_with_informative_previous()


@pytest.fixture
def url_extractor() -> UrlExtractor:
    return UrlExtractor()


@pytest.fixture
def url_categorizer() -> UrlCategorizer:
    return UrlCategorizer()


@pytest.fixture
def context_resolver() -> ContextResolver:
    return ContextResolver()


@pytest.fixture
def rule_classifier() -> RuleClassifier:
    return RuleClassifier()


@pytest.fixture
def hybrid_classifier() -> HybridClassifier:
    return HybridClassifier(use_transformer=False)
