from __future__ import annotations

from datetime import UTC, datetime

from lib.schemas.knowledge import Confidence, Knowledge, KnowledgeCategory, SurpriseLogEntry, SurpriseType


def test_knowledge_records_both_success_and_failure_conditions() -> None:
    knowledge = Knowledge(
        knowledge_id="K0001",
        title="earnings_revision_underreaction",
        category=KnowledgeCategory.VALIDATED_PATTERN,
        observation="上方修正後、数週間かけて株価がじわじわ上昇する傾向",
        hypothesis="アナリストの情報反映が遅い(underreaction)",
        evidence="BT0001, BT0002",
        sample_size=48,
        conditions_where_it_worked="流動性の低い中小型株、決算シーズン",
        conditions_where_it_failed="大型株、地合いが弱い局面",
        market_regime="円安局面",
        confidence=Confidence.MEDIUM,
        last_verified_at=datetime(2026, 8, 16, tzinfo=UTC),
        source_experiments=("BT0001", "BT0002"),
    )
    assert knowledge.category == KnowledgeCategory.VALIDATED_PATTERN
    assert "BT0001" in knowledge.source_experiments


def test_failed_pattern_is_also_a_valid_category() -> None:
    knowledge = Knowledge(
        knowledge_id="K0002",
        title="low_pbr_alone_underperforms",
        category=KnowledgeCategory.FAILED_PATTERN,
        observation="単純な低PBRスクリーニングはTOPIX比で有意な超過収益を生まなかった",
        hypothesis="低PBRのみではValue trapを排除できない",
        evidence="BT0010",
        sample_size=120,
        conditions_where_it_worked="該当なし",
        conditions_where_it_failed="全期間",
        market_regime=None,
        confidence=Confidence.LOW,
        last_verified_at=datetime(2026, 8, 16, tzinfo=UTC),
    )
    assert knowledge.category == KnowledgeCategory.FAILED_PATTERN


def test_surprise_log_entry() -> None:
    surprise = SurpriseLogEntry(
        surprise_id="SU0001",
        observed_at=datetime(2026, 8, 16, tzinfo=UTC),
        related_experiment_id="BT0001",
        related_paper_trade_id=None,
        expected="緩やかな上昇",
        actual="発表翌日にストップ高",
        surprise_type=SurpriseType.EXCEEDED_EXPECTATION,
    )
    assert surprise.surprise_type == SurpriseType.EXCEEDED_EXPECTATION
