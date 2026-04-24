from backend.services.url_categorizer import UrlCategorizer


def test_conversation_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://app.intercom.com/conversations/123") == "conversation"


def test_workflow_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://app.intercom.com/workflows/456") == "workflow"


def test_custom_action_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://app.intercom.com/actions/789") == "custom_action"


def test_help_center_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://help.intercom.com/en/articles/100") == "help_center"


def test_github_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://github.com/intercom/intercom/issues/1") == "github"


def test_loom_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://www.loom.com/share/abc") == "loom"


def test_unknown_url(url_categorizer: UrlCategorizer) -> None:
    assert url_categorizer.categorize("https://example.com/foo") == "other"
