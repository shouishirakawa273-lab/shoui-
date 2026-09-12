"""As-of Fundamental View(Phase4A、D0043): decision_at時点で利用可能だった
Fundamental Metricのみを返す。

外部API取得と分析を分離する(D0042「Backtest/Experimentの完全Offline原則」)。
この関数は`RevisionHistory`(事前に`lib.fundamentals.normalize.
build_revision_histories()`等で構築済みのもの)だけを受け取り、一切の外部呼び出しを
行わない。decision_atごとにJ-Quants APIへ問い合わせる構造にはしない。

未来のDisclosure・未来のForecast Revision・未来のCorrectionを絶対に含めない
(`RevisionHistory.as_of()`/`as_of_by_semantics()`が`available_at`/`published_at`
基準でフィルタする)。暗黙のForward Fillは行わない: あるSeriesについてdecision_at
時点で利用可能なVersionが無ければ、素直に`None`を返す(「直前のForecastを現在の
Forecastとして扱う」処理はここには実装しない。そのような処理が必要な場合は、
明示的なQuery Semanticsとして別途実装し、`DataLayer.DERIVED`として由来を残すこと)。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion


def as_of_by_semantics(
    history: RevisionHistory,
    decision_at: datetime,
    *,
    availability_semantics: AvailabilitySemantics,
    include_unknown_availability: bool = False,
) -> SourceVersion | None:
    """2種類のPIT研究(D0042)を区別してas_of解決する。

    - `MARKET_PUBLIC_AT`(Market Information Study、A系統): `published_at`基準。
    - `PROVIDER_AVAILABLE_AT`(Reproducible System Simulation、B系統、既定):
      既存`RevisionHistory.as_of()`をそのまま使う(`availability_basis=UNKNOWN`の
      Versionを既定で除外する安全側デフォルトを含む)。provider_available_atが
      UNKNOWNの場合にmarket_public_atへFallbackすることはしない
      (`RevisionHistory.as_of()`の除外ロジックがそのまま効く)。

    `include_unknown_availability`はB系統のみに作用する(`RevisionHistory.as_of()`
    への素通し)。Phase4Aでは`provider_available_at`のavailability_basisが常に
    `UNKNOWN`になる(D0043、実際のPolling Log等が無いため)。既定`False`のままだと
    B系統のas_ofは常に`None`を返す(=INSUFFICIENT_DATA相当、安全側)。ローカル環境で
    実際の観測ログ等からavailability_basisを`EXACT`/`OBSERVED`へ格上げできた場合や、
    未確認のまま許容してでも値を見たい場合のみ、呼び出し側が明示的に
    `True`を指定する。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at はtz-awareである必要があります")
    if availability_semantics == AvailabilitySemantics.MARKET_PUBLIC_AT:
        candidates = [v for v in history.versions if v.published_at is not None and v.published_at <= decision_at]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.published_at)  # type: ignore[arg-type,return-value]
    return history.as_of(decision_at, include_unknown_availability=include_unknown_availability)


def fundamentals_as_of(
    revision_histories: Mapping[str, RevisionHistory],
    decision_at: datetime,
    *,
    availability_semantics: AvailabilitySemantics = AvailabilitySemantics.PROVIDER_AVAILABLE_AT,
    include_unknown_availability: bool = False,
) -> dict[str, SourceVersion | None]:
    """series_id -> decision_at時点で利用可能な最新`SourceVersion`(無ければ`None`)。

    `None`は「そのSeriesについて、decision_at時点でまだ利用可能な値が無い」という
    As-of Query Outcomeを表す(Metric自体のStored Value State=`ValueAvailability`
    とは別軸、`lib.fundamentals.model`のモジュールDocstring参照)。
    """
    return {
        series_id: as_of_by_semantics(
            history,
            decision_at,
            availability_semantics=availability_semantics,
            include_unknown_availability=include_unknown_availability,
        )
        for series_id, history in revision_histories.items()
    }
