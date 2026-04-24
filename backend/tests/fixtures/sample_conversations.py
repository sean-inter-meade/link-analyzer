from datetime import datetime, timezone

from backend.models import ConversationMessage, AuthorType

BASE_DATE = datetime(2024, 1, 15, tzinfo=timezone.utc)


def _ts(minutes: int) -> datetime:
    return BASE_DATE.replace(minute=minutes)


def fixture_user_reports_broken_workflow() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text="Hi, I'm having trouble with a workflow",
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg2",
            author_type=AuthorType.USER,
            body_text="This workflow doesn't work at all https://app.intercom.com/workflows/123 - it keeps failing with a timeout",
            created_at=_ts(2),
            conversation_id="conv_test",
        ),
    ]


def fixture_admin_sends_url_after_intro() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text="The custom action is broken",
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg2",
            author_type=AuthorType.ADMIN,
            body_text="Try this one instead, it should work",
            created_at=_ts(2),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg3",
            author_type=AuthorType.ADMIN,
            body_text="https://app.intercom.com/actions/456",
            created_at=_ts(3),
            conversation_id="conv_test",
        ),
    ]


def fixture_bare_url_with_broken_previous() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text="Here's a broken example of the conversation",
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg2",
            author_type=AuthorType.USER,
            body_text="https://app.intercom.com/conversations/789",
            created_at=_ts(2),
            conversation_id="conv_test",
        ),
    ]


def fixture_admin_confirms_working() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text="Is this article accessible?",
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg2",
            author_type=AuthorType.ADMIN,
            body_text="This is working for me, can confirm https://help.intercom.com/en/articles/100",
            created_at=_ts(2),
            conversation_id="conv_test",
        ),
    ]


def fixture_multiple_urls_mixed() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.USER,
            body_text=(
                "Here are some examples. This one works https://github.com/intercom/intercom/issues/1 "
                "but this workflow is broken https://app.intercom.com/workflows/999 "
                "and here is a loom recording https://www.loom.com/share/abc123"
            ),
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
    ]


def fixture_neutral_with_informative_previous() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            id="msg1",
            author_type=AuthorType.ADMIN,
            body_text="This conversation shows the bug where Fin gives the wrong answer",
            created_at=_ts(1),
            conversation_id="conv_test",
        ),
        ConversationMessage(
            id="msg2",
            author_type=AuthorType.USER,
            body_text="https://app.intercom.com/conversations/555",
            created_at=_ts(2),
            conversation_id="conv_test",
        ),
    ]
