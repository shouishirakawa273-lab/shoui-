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
    """as_of時点でのUniverse解決結果。

    `survivorship_bias_unresolved=True`は、このUniverseが「現在上場している銘柄」を
    過去へ遡らせて構築されており、当時存在したが現在は上場廃止済みの銘柄を
    捕捉できていない可能性があることを示す。このSnapshotを使ったBacktestの結果は
    Survivorship biasが残存する前提で解釈すること(RESEARCH_RULES.md参照)。
    """

    as_of: datetime
    resolution: UniverseResolution
    codes: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""
    survivorship_bias_unresolved: bool = False


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


def _auto_detect_survivorship_bias(listings: Sequence[ListingRecord]) -> bool:
    """全てのlistingにdelisting_dateが無ければ、廃止銘柄を追跡できておらず
    (=現在の上場銘柄だけを過去へ遡らせている可能性が高く)Survivorship biasが
    残っていると推測する。1件でもdelisting_dateがあれば、少なくとも部分的には
    廃止銘柄を扱えているとみなす。"""
    return len(listings) > 0 and all(listing.delisting_date is None for listing in listings)


class ListingBasedUniverseProvider:
    """ListingRecordの集合からUniverseSnapshotを計算する素朴な実装。

    実データソースが無い場合(listingsが空)は DATA_UNAVAILABLE を返し、
    「投資可能銘柄が0件だった」という架空の結論を出さない。

    J-Quantsの``/listed/info``のように「現在の上場状況」しか分からないデータソースから
    構築した場合、`survivorship_bias_unresolved`を明示的にTrueにするか、
    (全listingにdelisting_dateが無い場合は)自動検出により`True`になる。
    """

    def __init__(self, listings: Sequence[ListingRecord], *, survivorship_bias_unresolved: bool = False) -> None:
        self._listings = tuple(listings)
        self._survivorship_bias_unresolved = survivorship_bias_unresolved or _auto_detect_survivorship_bias(self._listings)

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
        note = ""
        if self._survivorship_bias_unresolved:
            note = "delisting_dateが無いlistingのみのため、廃止銘柄を捕捉できていない可能性がある"
        return UniverseSnapshot(
            as_of=as_of,
            resolution=UniverseResolution.RESOLVED,
            codes=codes,
            note=note,
            survivorship_bias_unresolved=self._survivorship_bias_unresolved,
        )
