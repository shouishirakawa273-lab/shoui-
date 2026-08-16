"""Point-in-Time Universe: as_of時点で投資可能だった銘柄集合を返すInterface。

Survivorship bias排除の前提となる。実データ(上場日・廃止日等)が無い/不十分な場合に
架空の補完をせず、PARTIAL / UNRESOLVED / DATA_UNAVAILABLE を明示する
(数値を推測で埋めない方針)。

**Phase3Cで判明・確定した既知の制約(DECISIONS.md D0038/D0039参照)**:
- J-Quants API V2 `/v2/equities/master`の`date`パラメータは、実データによる
  確認済みSmoke Test(6502 東芝、as_of=2023-12-19では含まれ、
  as_of=2023-12-21では含まれない。DECISIONS.md D0039)により、真のPoint-in-Time
  上場状況(=当時存在したが現在は廃止済みの銘柄を含む)を返すことを確認済み。
  ただし、これは「decision_atごとにその日付を指定してMasterへ再問い合わせした場合」
  にのみ成り立つ確認結果である。`ListingBasedUniverseProvider`のように単一の
  Masterスナップショット(例: 期間末日のみを`date`に指定した1回分)を全期間の
  decision_atへ使い回す場合には、依然としてSurvivorship Biasが残る
  (`survivorship_bias_unresolved`/`PARTIAL`のまま)。真にdecision_atごとの
  PIT解決が必要な場合は`PitMasterUniverseProvider`を使うこと。
- 市場区分(Prime/Standard/Growth等)は2022年4月のTSE市場再編で大きく変わった。
  単一時点のMasterスナップショットからは、ある銘柄が過去のどの時点でどの市場区分に
  属していたかを復元できない。`ListingRecord.market`は「そのMasterスナップショット
  自身のas_of時点での区分」を表すに過ぎず、過去のdecision_atにおける市場区分としては
  使わないこと。また`market`は「投資対象の市場Scope」(Prime/Standard/Growth等)を
  表すに過ぎず、「普通株かどうか」を表すものではない(D0039)。普通株かどうかは
  `ListingRecord.instrument_type`(J-Quants Masterの商品区分フィールド、Provider仕様に
  沿って別途扱う)で判定する。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from lib.schemas.base import RecordMeta


class UniverseResolution(StrEnum):
    RESOLVED = "RESOLVED"  # 完全に解決できた(Survivorship Bias等の既知の欠落が無い)
    PARTIAL = "PARTIAL"  # 部分的に解決できたが、既知の欠落(Survivorship Bias等)が残る
    UNRESOLVED = "UNRESOLVED"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


@dataclass(kw_only=True, frozen=True)
class ListingRecord(RecordMeta):
    """銘柄1件の上場・取引可能期間に関する情報。

    `code`はResearch Lab内部Code(普通株4桁)。`provider_code`はJ-Quants等の
    Provider側の生の値(5桁等)を混同しないよう別途保持する
    (`lib.data_sources.ticker_codes`、DECISIONS.md D0036)。

    `market`と`instrument_type`は別概念であり混同しない(D0039)。`market`は
    投資対象の市場Scope(Prime/Standard/Growth等)、`instrument_type`は商品区分
    (普通株/ETF/REIT/優先株/外国株等)を表す。普通株判定には`instrument_type`を使う
    (`build_common_stock_universe`参照)。J-Quants Masterの実際のField名は
    ユーザー提供情報に基づき`ProdCat`相当を想定しているが、正確なField名・値の
    列挙はローカル環境での実データ確認が必要(未確定要素を含むためこの情報源を
    明示する)。
    """

    code: str
    market: str
    sector: str | None = None
    company_name: str | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    tradable_from: date | None = None
    tradable_until: date | None = None
    provider_code: str | None = None
    instrument_type: str | None = None


@dataclass(frozen=True)
class UniverseSnapshot:
    """as_of時点でのUniverse解決結果。

    `survivorship_bias_unresolved=True`は、このUniverseが「現在上場している銘柄」を
    過去へ遡らせて構築されており、当時存在したが現在は上場廃止済みの銘柄を
    捕捉できていない可能性があることを示す。この場合`resolution`は
    `UniverseResolution.PARTIAL`になる(RESOLVEDとは扱わない、D0038)。このSnapshotを
    使ったBacktestの結果はSurvivorship biasが残存する前提で解釈すること
    (RESEARCH_RULES.md参照)。
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
        if self._survivorship_bias_unresolved:
            # Survivorship Biasを解消できていない=完全解決ではないため、RESOLVEDとは
            # 扱わない(D0038)。実際に投資可能だった銘柄集合の下限(現在まで生き残った
            # 銘柄)は分かるが、上限(当時存在したが後に廃止された銘柄)は分からない。
            return UniverseSnapshot(
                as_of=as_of,
                resolution=UniverseResolution.PARTIAL,
                codes=codes,
                note="delisting_dateが無いlistingのみのため、廃止銘柄を捕捉できていない可能性がある"
                "(Survivorship Bias未解消、Universe下限のみ判明)",
                survivorship_bias_unresolved=True,
            )
        return UniverseSnapshot(
            as_of=as_of,
            resolution=UniverseResolution.RESOLVED,
            codes=codes,
            survivorship_bias_unresolved=False,
        )


@dataclass(frozen=True)
class PitCoverage:
    """PIT Master問い合わせ(`date`パラメータ)が正当と実データで確認されている期間。

    2023-12-19/2023-12-21をまたぐ6502(東芝)のMembership変化により、
    `/v2/equities/master`の`date`パラメータが真のPIT Snapshotを返すこと自体は
    確認済みだが(D0039)、それ以外の期間(特にこの確認より過去の期間)についても
    同様に機能するかは別途の確認が必要である。したがって`confirmed_from` /
    `confirmed_until`は「実際に確認できた範囲」を呼び出し側が明示的に渡す
    (このモジュール自身が「確認済み」を拡大解釈しない)。
    """

    confirmed_from: date
    confirmed_until: date

    def covers(self, target_date: date) -> bool:
        return self.confirmed_from <= target_date <= self.confirmed_until


class PitMasterUniverseProvider:
    """decision_atごとに`/v2/equities/master`をas_of=decision_atで再問い合わせし、
    真にPoint-in-TimeなUniverseSnapshotを解決するProvider(D0039)。

    `ListingBasedUniverseProvider`との違い: 後者は単一の静的なListingRecord集合を
    構築時に受け取り、`as_of()`ではそれをローカルにフィルタするだけ(=全期間で
    同じMasterスナップショットを使い回す)。本Providerは`master_fetcher`
    (通常は`adapter.fetch_equities_master(as_of=...)`を呼び出すCallable)を
    decision_atごとに実際に呼び出すため、D0035の`PriceHistorySource.as_of()`と同じ
    設計思想(全期間分を一度だけ事前計算して使い回さない)をUniverseにも適用する。

    `confirmed_coverage`の範囲外のas_ofについては、PIT性が未確認のため
    Master再取得そのものを行わず(不要なAPI呼び出しを避ける)、安全側の`PARTIAL`を
    返す。範囲内であっても、`master_fetcher`が空集合を返した場合は
    `DATA_UNAVAILABLE`とする(「投資可能銘柄が0件だった」という架空の結論を出さない)。

    decision_dateごとの重複問い合わせを避けるため、日付単位でSnapshotをキャッシュする
    (`BacktestEngine`側でも同様のキャッシュを持つが、本Provider単体で使う場合にも
    重複呼び出しを避けられるようにするため、二重にキャッシュする)。
    """

    def __init__(self, master_fetcher: Callable[[date], Sequence[ListingRecord]], *, confirmed_coverage: PitCoverage) -> None:
        self._master_fetcher = master_fetcher
        self._confirmed_coverage = confirmed_coverage
        self._cache: dict[date, UniverseSnapshot] = {}

    def as_of(self, as_of: datetime) -> UniverseSnapshot:
        if as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        target_date = as_of.date()
        if target_date in self._cache:
            return self._cache[target_date]

        if not self._confirmed_coverage.covers(target_date):
            snapshot = UniverseSnapshot(
                as_of=as_of,
                resolution=UniverseResolution.PARTIAL,
                note=(
                    f"PIT確認済み範囲({self._confirmed_coverage.confirmed_from}〜"
                    f"{self._confirmed_coverage.confirmed_until})外のため安全側に倒した"
                    "(Master再取得は行っていない、D0039)"
                ),
                survivorship_bias_unresolved=True,
            )
            self._cache[target_date] = snapshot
            return snapshot

        listings = self._master_fetcher(target_date)
        if not listings:
            snapshot = UniverseSnapshot(
                as_of=as_of,
                resolution=UniverseResolution.DATA_UNAVAILABLE,
                note=f"as_of={target_date}のMaster再取得結果が空でした",
            )
            self._cache[target_date] = snapshot
            return snapshot

        codes = tuple(sorted(listing.code for listing in listings if _is_tradable_on(listing, target_date)))
        snapshot = UniverseSnapshot(
            as_of=as_of,
            resolution=UniverseResolution.RESOLVED,
            codes=codes,
            note="PIT確認済みMaster(dateパラメータ)をdecision_atごとに再取得して解決(D0039)",
            survivorship_bias_unresolved=False,
        )
        self._cache[target_date] = snapshot
        return snapshot


@dataclass(frozen=True)
class CommonStockFilterResult:
    """`build_common_stock_universe`の結果。除外した件数・理由を必ず追跡できるようにする
    (ETF/REIT/優先株等が誤って普通株Universeへ混入していないことを監査できるように)。
    """

    included: tuple[ListingRecord, ...]
    excluded: tuple[ListingRecord, ...]
    excluded_instrument_types: Mapping[str, int]


def build_common_stock_universe(
    listings: Sequence[ListingRecord],
    *,
    common_stock_instrument_types: frozenset[str],
) -> CommonStockFilterResult:
    """普通株Universeを明示的に定義する(D0038/D0039)。

    `common_stock_instrument_types`は「普通株を表す商品区分(instrument_type)の集合」を
    呼び出し側が明示的に渡す(このモジュール自身は実際のJ-Quants商品区分Fieldの
    値・意味を検証しておらず、推測で決め打ちしない。DECISIONS.md D0038/D0039参照)。
    `listing.instrument_type`がこの集合に含まれないListingRecordは、ETF・REIT・
    優先株・外国株等(普通株以外)である可能性があるとみなし、除外する。
    **`listing.market`(Prime/Standard/Growth等の市場Scope)は普通株判定には使わない**
    (D0039、`market`と`instrument_type`は別概念)。

    **既定で「除外」側に倒す**: `common_stock_instrument_types`が空、または
    instrument_typeが不明(取得不可)な場合も、安全側に倒して除外する(誤って
    普通株Universeへ混入させるより、判断できない銘柄を除外してしまう方を選ぶ)。
    除外した銘柄とその理由(instrument_type別件数)は`CommonStockFilterResult`で
    必ず追跡できる。
    """
    included: list[ListingRecord] = []
    excluded: list[ListingRecord] = []
    excluded_instrument_types: dict[str, int] = {}
    for listing in listings:
        instrument_type = listing.instrument_type or "取得不可"
        if instrument_type in common_stock_instrument_types:
            included.append(listing)
        else:
            excluded.append(listing)
            excluded_instrument_types[instrument_type] = excluded_instrument_types.get(instrument_type, 0) + 1
    return CommonStockFilterResult(
        included=tuple(included),
        excluded=tuple(excluded),
        excluded_instrument_types=excluded_instrument_types,
    )


def check_company_name_consistency(expected_names: dict[str, str], listings: Sequence[ListingRecord]) -> list[str]:
    """手入力のTicker->会社名対応が、Listed Issue Masterと食い違っていないか確認する。

    会社名を手入力のCanonical Dataとして扱わない方針(Phase3A.1、DECISIONS.md D0033)の
    一環。手入力名は表示・ドキュメント用の参考情報にとどめ、Masterと矛盾する場合は
    ここで警告文字列を生成する(例外は投げない。呼び出し側でログ・表示に使う)。
    大文字小文字・全角半角の違いは区別せず、部分一致であれば一致とみなす
    (法人格表記の揺れ等を許容するため)。

    `listings`に対応するcodeが無い場合(Masterから解決できない場合)も、
    「確認できていない」ことを警告として返す(黙って一致扱いにしない)。
    """
    by_code = {listing.code: listing.company_name for listing in listings}
    warnings: list[str] = []
    for code, expected_name in expected_names.items():
        if code not in by_code:
            warnings.append(f"{code}: Masterに銘柄が見つからず、会社名'{expected_name}'を確認できません")
            continue
        actual_name = by_code[code]
        if actual_name is None:
            warnings.append(f"{code}: Masterに会社名が含まれておらず、'{expected_name}'を確認できません")
            continue
        normalized_expected = expected_name.strip().casefold()
        normalized_actual = actual_name.strip().casefold()
        if normalized_expected not in normalized_actual and normalized_actual not in normalized_expected:
            warnings.append(f"{code}: 手入力の会社名'{expected_name}'がMasterの'{actual_name}'と一致しません")
    return warnings
