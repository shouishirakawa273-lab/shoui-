"""Fundamental Evidence PIT Bugfix(独立修正、Phase4A追記): `disclosure_metric_to_evidence()`の
`source.available_at`が`market_public_at`へFallbackしていたBugの回帰テスト。

## Root Cause

旧実装は`available_at = envelope.market_public_at or envelope.retrieved_at`
としていた。`market_public_at`(市場公表時刻、A系統)は通常`provider_
available_at`(Provider経由で実際に参照可能になった時刻、B系統)より**早い**
ため、これを`available_at`へ代入すると、実際にはまだ研究所側で取得可能で
なかった時点を「利用可能だった」と誤認する(Future Leakage)。

例: market_public_at=15:00、実際のProvider配信=15:05、retrieved_at=15:06の
場合、旧実装は`available_at=15:00`としてしまい、`decision_at=15:03`時点で
Evidenceが「利用可能」と誤判定されうる(実際には15:06まで取得していない)。

## Fix

`DisclosureEnvelope`/`FundamentalMetric`/`SourceMetadata`のいずれも確認済み
`provider_available_at`を保持するFieldを持たない(現行Schemaの制約)。
したがって`source.available_at`には常に`envelope.retrieved_at`
(Observed Factとしての下限)を使う。`market_public_at`は`source.
published_at`(A系統)としてのみ設定し、`available_at`へはFallbackしない。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evidence.model import ValueAvailability
from lib.fundamentals.evidence import disclosure_metric_to_evidence
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)


def _build_envelope(*, market_public_at: datetime | None, retrieved_at: datetime) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id="ENV_TEST_1",
        provider_code="72030",
        internal_code="7203",
        disclosure_number="D1",
        document_type="FYFinancialStatements_Consolidated_IFRS",
        disclosure_date=market_public_at.date() if market_public_at is not None else None,
        disclosure_time=market_public_at.strftime("%H:%M") if market_public_at is not None else None,
        market_public_at=market_public_at,
        retrieved_at=retrieved_at,
    )


def _build_metric(envelope: DisclosureEnvelope, *, value: str = "120") -> FundamentalMetric:
    return FundamentalMetric(
        metric_id="MET_TEST_1",
        envelope_id=envelope.envelope_id,
        series_id="7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS",
        metric_type="operating_profit_current_year_forecast",
        raw_value=value,
        value=Decimal(value),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.COMPANY_FORECAST,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="FOP",
    )


# --- A. market_public_atがretrieved_atより早い場合 ---


def test_available_at_uses_retrieved_at_not_market_public_at_when_market_public_at_is_earlier() -> None:
    """Root Causeそのものの再現: market_public_at=15:00、retrieved_at=15:06の
    場合、available_atは15:06(retrieved_at)であり、15:00(market_public_at)
    ではないことを確認する。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)

    evidence = disclosure_metric_to_evidence(envelope, metric)

    assert evidence.source.published_at == market_public_at
    assert evidence.source.available_at == retrieved_at
    assert evidence.source.available_at != market_public_at


# --- B. provider availability UNKNOWNの場合にmarket_public_at Fallbackが存在しないこと ---


def test_available_at_never_falls_back_to_market_public_at_when_market_public_at_is_none() -> None:
    """market_public_atがNone(未確認)の場合でも、available_atは常に
    retrieved_atであり、Noneや別の推測値へFallbackしないことを確認する。"""
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=None, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)

    evidence = disclosure_metric_to_evidence(envelope, metric)

    assert evidence.source.published_at is None
    assert evidence.source.available_at == retrieved_at


@pytest.mark.parametrize(
    ("market_public_at", "retrieved_at"),
    [
        (datetime(2026, 8, 17, 15, 0, tzinfo=UTC), datetime(2026, 8, 17, 15, 6, tzinfo=UTC)),
        (None, datetime(2026, 8, 17, 15, 6, tzinfo=UTC)),
        (datetime(2026, 8, 17, 9, 0, tzinfo=UTC), datetime(2026, 8, 18, 9, 0, tzinfo=UTC)),
    ],
)
def test_available_at_always_equals_retrieved_at_regardless_of_market_public_at(
    market_public_at: datetime | None, retrieved_at: datetime
) -> None:
    """available_atが常にretrieved_atと一致し、market_public_atの値・有無に
    左右されないことをParametrizeで包括的に確認する(Fallback経路が一切
    存在しないことの回帰確認)。"""
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)
    evidence = disclosure_metric_to_evidence(envelope, metric)
    assert evidence.source.available_at == retrieved_at


# --- C. as_of between market_public_at and retrieved_at(B系統相当のEvidence Availability) ---


def test_evidence_is_not_usable_at_decision_at_between_market_public_at_and_retrieved_at() -> None:
    """decision_at=15:03(market_public_at=15:00とretrieved_at=15:06の間)では、
    `EvidenceRecord.is_usable_at()`がFalseを返すことを確認する(旧Bugでは
    available_at=15:00とされ、15:03時点で誤ってTrueになっていた)。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)
    evidence = disclosure_metric_to_evidence(envelope, metric)

    decision_at_between = datetime(2026, 8, 17, 15, 3, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_between) is False

    decision_at_after_retrieval = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_after_retrieval) is True

    decision_at_before_market_public = datetime(2026, 8, 17, 14, 59, tzinfo=UTC)
    assert evidence.is_usable_at(decision_at_before_market_public) is False


# --- D. tz-aware維持 ---


def test_available_at_and_published_at_stay_tz_aware() -> None:
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)
    evidence = disclosure_metric_to_evidence(envelope, metric)

    assert evidence.source.available_at.tzinfo is not None
    assert evidence.source.published_at is not None
    assert evidence.source.published_at.tzinfo is not None


def test_envelope_construction_rejects_tz_naive_retrieved_at() -> None:
    with pytest.raises(ValueError, match="retrieved_at"):
        DisclosureEnvelope(
            envelope_id="ENV_NAIVE",
            provider_code="72030",
            internal_code="7203",
            retrieved_at=datetime(2026, 8, 17, 15, 6),  # tz無し
        )


# --- E. Evidence Contentが解釈語(Bullish/Positive/Buy等)を一切含まないこと ---

_FORBIDDEN_INTERPRETATION_WORDS = (
    "bullish",
    "bearish",
    "buy",
    "sell",
    "positive",
    "negative",
    "好調",
    "悪化",
    "割安",
    "割高",
    "強気",
    "弱気",
)


def test_evidence_content_never_contains_interpretation_or_trading_language() -> None:
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope)
    evidence = disclosure_metric_to_evidence(envelope, metric)

    lowered_content = evidence.content.lower()
    for forbidden_word in _FORBIDDEN_INTERPRETATION_WORDS:
        assert forbidden_word not in lowered_content


# --- F. 単一Metricから "100→120" のようなRevision文を生成しないこと ---


def test_evidence_content_does_not_state_a_revision_from_old_to_new_value() -> None:
    """`disclosure_metric_to_evidence()`は単一の`FundamentalMetric`(1つの開示
    された値)のみを引数に取り、旧Value/新Valueの比較文言を一切生成しない
    ことを確認する(単一Metricからのrevision Statement生成禁止)。"""
    market_public_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    retrieved_at = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
    envelope = _build_envelope(market_public_at=market_public_at, retrieved_at=retrieved_at)
    metric = _build_metric(envelope, value="120")
    evidence = disclosure_metric_to_evidence(envelope, metric)

    assert "→" not in evidence.content
    assert "から" not in evidence.content
    assert "変更" not in evidence.content
    assert "修正" not in evidence.content
    assert "revision" not in evidence.content.lower()
    # 開示された値そのもの(120)は含まれるが、比較対象の旧Valueは存在しない。
    assert "120" in evidence.content


def test_disclosure_metric_to_evidence_signature_accepts_exactly_one_metric() -> None:
    """関数SignatureがFundamentalMetricを1つしか受け取らないことを構造的に
    確認する(複数Metricを比較してRevisionを推論する経路が存在しないことの
    構造的保証)。"""
    import inspect

    sig = inspect.signature(disclosure_metric_to_evidence)
    metric_params = [p for name, p in sig.parameters.items() if name == "metric"]
    assert len(metric_params) == 1
    assert "metrics" not in sig.parameters
    assert "old_metric" not in sig.parameters
    assert "new_metric" not in sig.parameters


# --- G. Replayはretrieved_atを保存時の値のまま保持し、Replay実行時刻へ上書きしない ---


def test_offline_replay_preserves_original_retrieved_at_not_replay_time(tmp_path: Path) -> None:
    """外部Review(Copilot)で追加確認された項目: RawSnapshotStoreへの保存 ->
    再読込 -> 再Parseという経路でも、`retrieved_at`が保存時点の値のまま
    保持され、Replayを実行した「現在時刻」へ上書きされないことを確認する。

    `parse_financial_summary_payload()`は`retrieved_at`を必須Keyword引数と
    して要求し、内部で`datetime.now()`等を呼び出さない(構造的にReplay時刻を
    生成する経路が無い)。この構造を、実際にSnapshot保存 -> Manifest経由での
    再読込という経路で確認する。
    """
    import json

    from lib.data_sources.base import RawFetchResult
    from lib.fundamentals.normalize import parse_financial_summary_payload
    from lib.snapshot import RawSnapshotStore

    original_retrieved_at = datetime(2024, 5, 8, 9, 0, tzinfo=UTC)
    raw_payload = [
        {
            "Code": "72030",
            "DiscNo": "D1",
            "DocType": "FYFinancialStatements_Consolidated_IFRS",
            "DiscDate": "2024-05-08",
            "DiscTime": "15:00",
            "OP": "1000",
        }
    ]
    fetch_result = RawFetchResult(
        source="jquants",
        endpoint="/v2/fins/summary",
        request_parameters={"codes": ["7203"], "from": "2024-01-01", "to": "2024-12-31"},
        retrieved_at=original_retrieved_at,
        data_period="2024-01-01/2024-12-31",
        response_schema_version="v2",
        payload=raw_payload,
    )

    store = RawSnapshotStore(tmp_path)
    manifest = store.save(fetch_result, snapshot_id="SNAP_REPLAY_TEST")

    # Manifest自体が保存時点のretrieved_atをそのまま記録している
    # (Replay実行時刻ではない)。
    assert datetime.fromisoformat(manifest.retrieved_at) == original_retrieved_at

    # 実際のReplay経路: 保存済みPayloadを読み込み、Manifestに記録された
    # retrieved_atをそのまま使って再Parseする(現在時刻を新たに生成しない)。
    _loaded_manifest, loaded_payload = store.load("jquants", "SNAP_REPLAY_TEST")
    replay_retrieved_at = datetime.fromisoformat(_loaded_manifest.retrieved_at)
    assert replay_retrieved_at == original_retrieved_at

    envelopes, _metrics = parse_financial_summary_payload(loaded_payload, retrieved_at=replay_retrieved_at)
    assert envelopes[0].retrieved_at == original_retrieved_at

    # 参考: ManifestはJSONへSerializeされてもtz情報を保つ(往復整合性)。
    assert json.loads(json.dumps({"retrieved_at": manifest.retrieved_at}))["retrieved_at"] == manifest.retrieved_at
