"""Data Catalog: どのSourceに何のDataがあり、どの範囲でPIT利用可能かを検索可能にする。

Phase3D(D0040)の目的は「J-Quantsだけに依存しない情報基盤」を作ることであり、
将来Source(EDINET/TDnet/Company IR/Macro統計/Global Market/News/Consensus/Idea等)が
増えても研究所本体を作り直さずに済むよう、Source固有の実装ではなく共通のCatalog/
Capability構造を先に用意する。

**このモジュール自身は実際の外部APIへ接続しない。** `DatasetDescriptor`はSourceの
メタデータ(Coverage・更新頻度・PIT可否・Authority Class等)を記述するだけであり、
実装状況(`ImplementationStatus`)を明示することで「Catalogに載っているが未実装」を
「実際に接続済み」と混同しないようにする(数値・状態を推測で埋めない方針)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class DataCapability(StrEnum):
    """研究所が扱うDataの種類(Sourceを跨いだ横断的な分類)。"""

    MARKET_PRICE = "MARKET_PRICE"
    FUNDAMENTAL = "FUNDAMENTAL"
    DISCLOSURE = "DISCLOSURE"
    POSITIONING = "POSITIONING"
    EXPECTATIONS = "EXPECTATIONS"
    MACRO = "MACRO"
    GLOBAL_MARKET = "GLOBAL_MARKET"
    NEWS = "NEWS"
    IDEA = "IDEA"


class SourceAuthorityClass(StrEnum):
    """Sourceそのものの権威づけ(内容の正しさではなく、情報の出所としての位置づけ)。

    **これは信頼度の単純な順位・点数ではなく、Sourceの性質を表すカテゴリである**
    (D0041)。`PRIMARY_OFFICIAL=100点、SOCIAL=10点`のような単純なスコアリングや、
    Authority Classに基づく多数決・重み付け投票に使ってはならない。

    **重要**: `PRIMARY_OFFICIAL`だからといって、その内容の解釈(将来予測・経営者の
    見通し等)まで正しいとは限らない。「会社が発表した数字」(FACT)と
    「会社経営陣の将来見通し」(CLAIM)は別概念であり、Authority Classだけで
    Evidence Typeを代替しない(`lib.evidence.model.EvidenceType`参照)。例えば
    企業IR(`COMPANY_PRIMARY`)は「営業利益予想を100億円と発表した」という事実の
    確認には非常に強いSourceである一方、「今後も需要は堅調である」という経営陣の
    将来見通しの真偽まで自動的に高信頼とみなしてはならない。**Source Authority
    (出所の位置づけ)とEvidence Content(内容そのものの信頼性)は分離して扱う。**
    """

    PRIMARY_OFFICIAL = "PRIMARY_OFFICIAL"  # 取引所・監督当局・政府統計等
    COMPANY_PRIMARY = "COMPANY_PRIMARY"  # 発行体自身の開示・IR
    VERIFIED_SECONDARY = "VERIFIED_SECONDARY"  # 検証可能な二次情報(大手報道機関等)
    SECONDARY = "SECONDARY"  # その他の二次情報
    SOCIAL = "SOCIAL"  # SNS等
    USER_SUPPLIED = "USER_SUPPLIED"  # ユーザーが手動で投入した情報


class PrimaryOrSecondary(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


class ImplementationStatus(StrEnum):
    """CatalogにDatasetとして記述されていることと、実際に接続済みであることを区別する。"""

    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"  # Catalog上の定義のみ(Phase3Dのデフォルト)
    FIXTURE_ONLY = "FIXTURE_ONLY"  # 合成データでのみ疎通確認済み
    SKELETON = "SKELETON"  # 実仕様に基づくAdapter骨格はあるが実接続はまだ
    CONNECTED = "CONNECTED"  # 実際にAPI/ファイルから取得できる状態


@dataclass(kw_only=True, frozen=True)
class SourceMetadata:
    """1件のEvidence/Recordが由来するSourceの共通メタデータ。

    `retrieved_at`(研究所がいつ取得したか)と`published_at`(発行者がいつ公表したか)、
    `available_at`(市場参加者が当時実際に参照可能になった日時)は別概念であり、
    混同しない(`lib.point_in_time`と同じ区別をMulti-Sourceへ拡張する、D0040)。
    `effective_at`は必要な場合のみ設定する(例: 制度変更の施行日のように、
    公表日と効力発生日がずれるケース)。

    `source_authority_class`は出所の位置づけであり、内容の真偽を保証しない
    (`SourceAuthorityClass`のDocstring参照)。
    """

    source_id: str
    source_type: str  # 例: "TDNET", "EDINET", "COMPANY_IR", "BOJ", "X" 等(自由記述、Enumで縛らない)
    provider_name: str
    source_authority_class: SourceAuthorityClass
    primary_or_secondary: PrimaryOrSecondary
    retrieved_at: datetime
    published_at: datetime | None
    available_at: datetime
    effective_at: date | None = None
    source_url: str | None = None
    license_or_usage_note: str | None = None
    content_hash: str | None = None
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at / available_at はtz-awareである必要があります")
        if self.published_at is not None and self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class DatasetDescriptor:
    """Catalog上の1データセットの記述。実装状況・Coverage・PIT可否等を検索可能にする。"""

    dataset_id: str
    source_id: str
    capability: DataCapability
    authority_class: SourceAuthorityClass
    implementation_status: ImplementationStatus = ImplementationStatus.NOT_IMPLEMENTED
    coverage_start: date | None = None
    coverage_end: date | None = None
    update_frequency: str = "取得不可"
    pit_available: bool = False
    applicable_codes: tuple[str, ...] | None = None  # None = 銘柄非依存(全銘柄/対象外)
    applicable_countries: tuple[str, ...] = field(default_factory=tuple)
    applicable_sectors: tuple[str, ...] = field(default_factory=tuple)
    cost_or_plan_dependency: str = "取得不可"
    known_limitations: str = ""
    notes: str = ""


class SourceCatalog:
    """DatasetDescriptorの集合を検索可能にする。将来Agentが
    「このResearch Questionに必要なDataは何か」をここから選べるようにする。
    """

    def __init__(self, datasets: Sequence[DatasetDescriptor] = ()) -> None:
        self._by_id: dict[str, DatasetDescriptor] = {}
        for dataset in datasets:
            self.register(dataset)

    def register(self, dataset: DatasetDescriptor) -> None:
        if dataset.dataset_id in self._by_id:
            raise ValueError(f"dataset_id={dataset.dataset_id} は既にCatalogへ登録されています(重複禁止)")
        self._by_id[dataset.dataset_id] = dataset

    def all(self) -> tuple[DatasetDescriptor, ...]:
        return tuple(self._by_id.values())

    def get(self, dataset_id: str) -> DatasetDescriptor | None:
        return self._by_id.get(dataset_id)

    def find(
        self,
        *,
        capability: DataCapability | None = None,
        code: str | None = None,
        country: str | None = None,
        sector: str | None = None,
        implementation_status: ImplementationStatus | None = None,
    ) -> tuple[DatasetDescriptor, ...]:
        """条件に合致するDatasetDescriptorを返す(全条件AND、指定した条件のみ絞り込む)。

        `code`/`country`/`sector`は、Datasetが`applicable_*`を明示している場合のみ
        絞り込みに使う。`applicable_codes=None`(銘柄非依存)は`code`指定時も常に含める。
        """
        results = []
        for dataset in self._by_id.values():
            if capability is not None and dataset.capability != capability:
                continue
            if implementation_status is not None and dataset.implementation_status != implementation_status:
                continue
            if code is not None and dataset.applicable_codes is not None and code not in dataset.applicable_codes:
                continue
            if country is not None and dataset.applicable_countries and country not in dataset.applicable_countries:
                continue
            if sector is not None and dataset.applicable_sectors and sector not in dataset.applicable_sectors:
                continue
            results.append(dataset)
        return tuple(results)
