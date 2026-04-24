from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AuthorType(str, Enum):
    USER = "user"
    LEAD = "lead"
    ADMIN = "admin"
    FIN = "fin"
    BOT = "bot"
    OTHER = "other"


class ConversationMessage(BaseModel):
    id: str
    author_type: AuthorType
    body_text: str
    created_at: datetime
    conversation_id: str
