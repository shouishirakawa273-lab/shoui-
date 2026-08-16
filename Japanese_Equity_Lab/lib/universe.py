"""Point-in-Time Universe: as_of時点で投資可能だった銘柄集合を返すInterface。

Survivorship bias排除の前提となる。実データ(上場日・廃止日等)が無い/不十分な場合に
架空の補完をせず、UNRESOLVED / DATA_UNAVAILABLE を明示する(数値を推測で埋めない方針)。
Phase1.1ではInterfaceと、synthetic dataによる素朴な実装のみを提供する。
実際のデータソース(証券コード一覧・上場/廃止日等)との連携はPhase2以降。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from lib.schemas.base import RecordMeta


class UniverseResolution(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(kw_only=True, frozen=True)
class ListingRecord(RecordMeta):
    """銘柄1件の上場・取引可能期間に関する情報。"""

    code: str
    market: str
    sector: str | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    tradable_from: date | None = None
    tradable_until: date | None = None


@dataclass(frozen=True)
class UniverseSnapshot:
    """as_of時点でのUniverse解決結果。"""

    as_of: datetime
    resolution: UniverseResolution
    codes: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


class UniverseProvider(Protocol):
    """as_of時点で投資可能だった銘柄集合を返すInterface。"""

    def as_of(self, as_of: datetime) -> UniverseSnapshot: ...


def _is_tradable_on(listing: ListingRecord, target_date: date) -> bool:
    if listing.listing_date is not None and target_date < listing.listing_date:
        return False
    if listing.delisting_date is not None and target_date >= listing.delisting_date:
        return False
    if listing.tradable_from is not None and target_date < listing.tradable_from:
        return False
    if listing.tradable_until is not None and target_date > listing.tradable_until:
        return False
    return True


class ListingBasedUniverseProvider:
    """ListingRecordの集合からUniverseSnapshotを計算する素朴な実装(synthetic test用)。

    実データソースが無い場合(listingsが空)は DATA_UNAVAILABLE を返し、
    「投資可能銘柄が0件だった」という架空の結論を出さない。
    """

    def __init__(self, listings: Sequence[ListingRecord]) -> None:
        self._listings = tuple(listings)

    def as_of(self, as_of: datetime) -> UniverseSnapshot:
        if as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if not self._listings:
            return UniverseSnapshot(
                as_of=as_of,
                resolution=UniverseResolution.DATA_UNAVAILABLE,
                note="listing dataが登録されていません",
            )
        target_date = as_of.date()
        codes = tuple(sorted(listing.code for listing in self._listings if _is_tradable_on(listing, target_date)))
        return UniverseSnapshot(as_of=as_of, resolution=UniverseResolution.RESOLVED, codes=codes)
