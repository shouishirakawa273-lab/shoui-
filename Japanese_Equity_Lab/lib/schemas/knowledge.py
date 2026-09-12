"""再利用可能な知見(成功・失敗の両方)とSurprise Log。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.schemas.base import RecordMeta


class KnowledgeCategory(StrEnum):
    VALIDATED_PATTERN = "VALIDATED_PATTERN"
    FAILED_PATTERN = "FAILED_PATTERN"
    MARKET_REGIME = "MARKET_REGIME"
    SECTOR_PATTERN = "SECTOR_PATTERN"
    BEHAVIORAL_BIAS = "BEHAVIORAL_BIAS"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(kw_only=True, frozen=True)
class Knowledge(RecordMeta):
    knowledge_id: str
    title: str
    category: KnowledgeCategory
    observation: str
    hypothesis: str
    evidence: str
    sample_size: int
    conditions_where_it_worked: str
    conditions_where_it_failed: str
    market_regime: str | None
    confidence: Confidence
    last_verified_at: datetime
    source_experiments: tuple[str, ...] = field(default_factory=tuple)


class SurpriseType(StrEnum):
    EXCEEDED_EXPECTATION = "EXCEEDED_EXPECTATION"
    OPPOSITE_RESULT = "OPPOSITE_RESULT"
    REGIME_SPECIFIC = "REGIME_SPECIFIC"


@dataclass(kw_only=True, frozen=True)
class SurpriseLogEntry(RecordMeta):
    """予想と違ったこと(良い意味でも悪い意味でも)をKnowledge候補として記録する。"""

    surprise_id: str
    observed_at: datetime
    related_experiment_id: str | None
    related_paper_trade_id: str | None
    expected: str
    actual: str
    surprise_type: SurpriseType
    notes: str = ""
