"""投資アイデアの受信箱(03_idea_inbox/)に対応するschema。

X投稿・YouTubeコメント等は「事実」や「買い推奨」として扱わず、
あくまでHypothesis Generatorの材料として扱う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.schemas.base import RecordMeta


class IdeaSourceType(StrEnum):
    YOUTUBE = "YOUTUBE"
    YOUTUBE_COMMENT = "YOUTUBE_COMMENT"
    X = "X"
    PAPER = "PAPER"
    BLOG = "BLOG"
    IR = "IR"
    MANUAL = "MANUAL"


class SourceReliability(StrEnum):
    """情報源そのものの信頼性(内容の正しさではなく、事実確認のしやすさの目安)。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class IdeaStatus(StrEnum):
    NEW = "NEW"
    REVIEWED = "REVIEWED"
    PROMOTED_TO_HYPOTHESIS = "PROMOTED_TO_HYPOTHESIS"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


@dataclass(kw_only=True, frozen=True)
class Idea(RecordMeta):
    idea_id: str
    discovered_at: datetime
    source_type: IdeaSourceType
    source_url: str | None
    source_author: str | None
    published_at: datetime | None
    original_claim: str
    ai_summary: str
    target_company: str | None = None
    target_sector: str | None = None
    time_horizon: str | None = None
    possible_mechanism: str | None = None
    testable_hypothesis: str | None = None
    required_data: tuple[str, ...] = field(default_factory=tuple)
    related_ideas: tuple[str, ...] = field(default_factory=tuple)
    source_reliability: SourceReliability = SourceReliability.UNKNOWN
    status: IdeaStatus = IdeaStatus.NEW
