"""LATEST_REPORTED_FY_PERの選定・計算(D0077)。

Price Selector(`session_close_at` PIT)・Fundamental Denominator(A系統
`MARKET_PUBLIC_AT`)・Corporate Action Guardを組み合わせ、fail closedで
`LatestReportedFyPerRecord`を構築する。既存の`RawOHLCVBar`/
`session_close_at`/`detect_corporate_action_events_from_equity_bars`
(呼び出し側が渡す)/`fundamentals_as_of`が返す`SourceVersion`をそのまま
再利用し、新しいPrice/Fundamentals取得経路は作らない。

**Denominator選定は呼び出し側の責務(要件v1-4)**: この関数自体は
`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`を呼ばない
(Series選定はD0075のBridgeにすでに存在し、二重実装しない)。呼び出し側が
FY実績・連結のEPS series_idについてこの選定を行った結果(`SourceVersion`
+ その元になった`FundamentalMetric`/`DisclosureEnvelope`)を渡す。この
関数はそれが本当にFY実績・連結・EPSであることを再検証する(fail closed、
Defense-in-depth)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from lib.errors import LookAheadBiasError
from lib.evidence.model import SourceVersion
from lib.fundamentals.model import ActualOrForecast, ConsolidationScope, DisclosureEnvelope, FundamentalMetric, PeriodType
from lib.market_calendar import session_close_at
from lib.schemas.price_data import CorporateAction, RawOHLCVBar
from lib.valuation.model import (
    DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED,
    CorporateActionBasisStatus,
    LatestReportedFyPerRecord,
)

_REQUIRED_METRIC_TYPE = "eps"


def select_latest_close_bar(raw_bars: Sequence[RawOHLCVBar], *, as_of: datetime) -> RawOHLCVBar | None:
    """as_of時点でSession Closeが確定済みの最新Barを選ぶ(要件v1-3)。

    `session_close_at(bar.session_date) <= as_of`を満たすBarの中から
    最新(session_dateが最大)のものを返す。Intraday Priceを推測しない
    (満たすBarが1件も無ければ`None`)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")
    candidates = [b for b in raw_bars if session_close_at(b.session_date) <= as_of]
    if not candidates:
        return None
    return max(candidates, key=lambda b: b.session_date)


def _has_share_basis_action_in_window(events: Sequence[CorporateAction], *, window_start: date, window_end: date) -> bool:
    """`window_start <= effective_date <= window_end`(両端Inclusive、要件v1-5の
    「fiscal-period end以後 かつ selected price session date以前」という表現通り)に
    該当するCorporate Action Eventが1件でもあるか。

    `detect_corporate_action_events_from_equity_bars()`が返すEventは種別未断定
    (`CorporateActionType.ADJUSTMENT_EVENT`、Split/Reverse-Splitのどちらかを断定
    しない)だが、v1では種別を問わず「Windowに存在すること」自体でGuardする
    (推測でSplit/Reverse-Splitを断定しない、fail closed優先)。
    """
    return any(window_start <= e.effective_date <= window_end for e in events)


def build_latest_reported_fy_per(
    *,
    entity_code: str,
    as_of: datetime,
    raw_bars: Sequence[RawOHLCVBar],
    corporate_action_events: Sequence[CorporateAction],
    eps_version: SourceVersion,
    eps_metric: FundamentalMetric,
    eps_envelope: DisclosureEnvelope,
) -> LatestReportedFyPerRecord | None:
    """LATEST_REPORTED_FY_PERをfail closedで構築する(要件v1-3〜6)。

    **`None`の意味(Silent Excludeではなく、呼び出し側が明示的に判定できる
    「値が無い」状態)**:
    - as_of時点で選定可能なPrice Barが無い(まだ大引けが確定していない等)。
    - `price_bar.close`がNone(値が存在しない)。
    - Corporate Action GuardがWindow内でEventを検出した(Share Basis不整合の
      可能性を排除できないため、fail closed。要件v1-5「生成しない」)。

    **例外を送出する場合(呼び出し側の入力そのものが契約に反する場合)**:
    - `eps_metric`がFY実績・連結・EPSでない(`ValueError`、要件v1-4の必須
      条件違反)。
    - `eps_version.published_at`がUNKNOWN(`ValueError`、値を推測しない)。
    - `eps_version.published_at`がas_ofより後(`LookAheadBiasError`、Future
      Disclosure Leakage)。
    - PriceとEPSのEntity Codeが一致しない(`ValueError`)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    if (
        eps_metric.metric_type != _REQUIRED_METRIC_TYPE
        or eps_metric.actual_or_forecast != ActualOrForecast.ACTUAL
        or eps_metric.period_type != PeriodType.FY
        or eps_metric.consolidation_scope != ConsolidationScope.CONSOLIDATED
    ):
        raise ValueError(
            "eps_metricはFY実績・連結のEPSである必要があります(fail closed): "
            f"metric_type={eps_metric.metric_type!r}, actual_or_forecast={eps_metric.actual_or_forecast.value!r}, "
            f"period_type={eps_metric.period_type.value!r}, consolidation_scope={eps_metric.consolidation_scope.value!r}"
        )
    if eps_metric.value is None:
        raise ValueError(f"metric_id={eps_metric.metric_id}: value_availability=PRESENTのはずですがvalueがNoneです")
    if eps_metric.envelope_id != eps_envelope.envelope_id:
        raise ValueError(
            f"eps_metric.envelope_id({eps_metric.envelope_id})とeps_envelope.envelope_id"
            f"({eps_envelope.envelope_id})が一致しません"
        )
    if eps_envelope.internal_code != entity_code:
        raise ValueError(f"eps_envelope.internal_code({eps_envelope.internal_code})がentity_code({entity_code})と一致しません")
    if eps_version.published_at is None:
        raise ValueError(
            f"source_version_id={eps_version.source_version_id}: published_at(market_public_at)がUNKNOWNのため"
            "LATEST_REPORTED_FY_PERを計算できません(fail closed、値を推測しない)"
        )
    if eps_version.published_at > as_of:
        raise LookAheadBiasError(
            f"source_version_id={eps_version.source_version_id}: published_at({eps_version.published_at.isoformat()})が"
            f"as_of({as_of.isoformat()})より後です(Future Disclosure Leakage防止)"
        )
    if eps_envelope.current_period_end is None:
        raise ValueError(
            f"envelope_id={eps_envelope.envelope_id}: current_period_endが不明のためCorporate Action Guardを実行できません"
        )

    price_bar = select_latest_close_bar(raw_bars, as_of=as_of)
    if price_bar is None:
        return None
    if price_bar.code != entity_code:
        raise ValueError(f"raw_barsのCode({price_bar.code})がentity_code({entity_code})と一致しません")
    if price_bar.close is None:
        return None

    fiscal_period_end = eps_envelope.current_period_end
    price_date = price_bar.session_date
    if price_date < fiscal_period_end:
        # Price日がFY末より前(通常はas_of>=published_atのGuardで排除されるはずだが、
        # 直接呼び出し等の誤用に備えfail closedにする)。
        return None

    if _has_share_basis_action_in_window(corporate_action_events, window_start=fiscal_period_end, window_end=price_date):
        return None

    price_value = Decimal(str(price_bar.close))
    eps_value = eps_metric.value
    multiple = price_value / eps_value

    return LatestReportedFyPerRecord(
        entity_code=entity_code,
        as_of=as_of,
        price_date=price_date,
        price_value=price_value,
        price_available_at=session_close_at(price_date),
        denominator_type=DENOMINATOR_TYPE_FY_ACTUAL_EPS_CONSOLIDATED,
        eps_value=eps_value,
        fiscal_period_end=fiscal_period_end,
        published_at=eps_version.published_at,
        source_version_id=eps_version.source_version_id,
        consolidation_scope=eps_metric.consolidation_scope.value,
        accounting_standard=eps_metric.accounting_standard,
        calculation_expression=(
            f"price_close({price_date.isoformat()})={price_value} / "
            f"fy_actual_eps_consolidated({fiscal_period_end.isoformat()})={eps_value}"
        ),
        multiple=multiple,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


__all__ = ["build_latest_reported_fy_per", "select_latest_close_bar"]
