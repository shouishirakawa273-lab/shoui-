"""`decision_at` 時点で見えていたVersionの列挙(Step 3共通)。

`fundamentals_as_of()` は「その時点の最新1件」を返す。スクリーナーは改定の履歴や
期ごとの推移そのものを見るので、同じ可視性判定を全Versionへ適用して並べる必要が
ある。判定ロジックを1箇所に集約し、推移側と予想改定側で食い違わないようにする。
"""

from __future__ import annotations

from datetime import datetime

from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion


def visible_versions(
    history: RevisionHistory,
    decision_at: datetime,
    *,
    availability_semantics: AvailabilitySemantics,
    include_unknown_availability: bool = False,
) -> list[SourceVersion]:
    """`decision_at` 時点で見えていたVersionを古い順に返す。

    `MARKET_PUBLIC_AT` は `published_at` 基準。`published_at` が無いVersionは
    「いつ公開されたか不明」なので含めない(推測で補完しない)。

    `PROVIDER_AVAILABLE_AT` は `available_at` 基準で、`availability_basis` が
    `UNKNOWN` のVersionを既定で除外する。Phase4Aでは実際の取得ログが無く常に
    `UNKNOWN` になるため、既定のままだと空になる。それは不具合ではなく安全側の
    既定であり、呼び出し側が `include_unknown_availability=True` を明示した場合
    のみ含める(`lib/fundamentals/view.py` と同じ契約)。

    Raises:
        ValueError: `decision_at` がtz-naiveの場合。
    """
    if decision_at.tzinfo is None:
        raise ValueError(f"decision_at must be timezone-aware: {decision_at!r}")

    if availability_semantics is AvailabilitySemantics.MARKET_PUBLIC_AT:
        published = [v for v in history.versions if v.published_at is not None and v.published_at <= decision_at]
        # published_at は上の内包表記で非Noneに絞り込み済み。
        return sorted(published, key=lambda v: (v.published_at or datetime.min, v.source_version_id))

    available = [
        v
        for v in history.versions
        if v.available_at <= decision_at and (include_unknown_availability or v.availability_basis.value != "UNKNOWN")
    ]
    return sorted(available, key=lambda v: (v.available_at, v.source_version_id))
