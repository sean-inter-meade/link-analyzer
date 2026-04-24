from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ExampleStatus(str, Enum):
    WORKING_EXAMPLE = "working_example"
    BROKEN_EXAMPLE = "broken_example"
    NEUTRAL_OR_UNKNOWN = "neutral_or_unknown"


class UrlType(str, Enum):
    CONVERSATION = "conversation"
    WORKFLOW = "workflow"
    CUSTOM_ACTION = "custom_action"
    ARTICLE = "article"
    HELP_CENTER = "help_center"
    LOOM = "loom"
    GITHUB = "github"
    OTHER = "other"
    EXCLUDED = "excluded"


class ContextReason(str, Enum):
    CURRENT_MESSAGE_HAS_MEANINGFUL_TEXT = "current_message_has_meaningful_text"
    ADMIN_MESSAGE_REFERENCES_LINK = "admin_message_references_link"
    PREVIOUS_MESSAGE_USED_DUE_TO_NEUTRAL = "previous_message_used_due_to_neutral"
    COMBINED_CONTEXT_USED_DUE_TO_SPARSE_TEXT = "combined_context_used_due_to_sparse_text"
    BARE_URL_FALLBACK_TO_PREVIOUS = "bare_url_fallback_to_previous"
    NO_CONTEXT_AVAILABLE = "no_context_available"


class ClassificationSignals(BaseModel):
    positive_phrases: list[str] = Field(default_factory=list)
    negative_phrases: list[str] = Field(default_factory=list)
    neutral_phrases: list[str] = Field(default_factory=list)
    rule_score: float = 0.0
    transformer_score: Optional[float] = None
    fallback_used: bool = False
    url_type_match: Optional[str] = None


class ExtractedLink(BaseModel):
    url: str
    message_id: str
    message_author_type: str
    message_created_at: datetime
    anchor_text: Optional[str] = None
    surrounding_text: str
    selected_context_text: str
    selected_context_message_id: str
    selected_context_author_type: str
    selected_context_reason: str
    url_type: str
    example_status: str
    confidence: float
    signals: ClassificationSignals


class LinkGroup(BaseModel):
    example_status: str
    items: list[ExtractedLink]


class AnalysisSummary(BaseModel):
    working_count: int = 0
    broken_count: int = 0
    unknown_count: int = 0


class AnalysisResponse(BaseModel):
    conversation_id: str
    summary: AnalysisSummary
    links: list[ExtractedLink]
    groups: list[LinkGroup]
    problem_summary: str = ""


class AnalyzeRequest(BaseModel):
    conversation_id: str


class AnalyzePreviewRequest(BaseModel):
    messages: list[dict]
