"""Evidence Model: FACT/CLAIM/INTERPRETATION/OPINION/IDEAを同一Fieldへ潰さない(D0040)。

## Epistemic Neutrality / Anti-Confirmation原則

DEFAULT PROCESS = ADVERSARIAL。CONCLUSION = NEUTRAL UNTIL SUPPORTED。

研究所は投資仮説に立証責任を課し、Negative Evidence / Alternative Explanation /
Missing Evidence / Contradictory Evidence / Priced-in Risk / Falsification Conditionを
探索できる構造を持つ。ただし「反証すること」自体を目的化せず、否定方向へのバイアスも
禁止する。**`EvidenceRecord`自身は特定のHypothesisに対するPositive/Negativeを
一切保持しない**(Evidenceは常にHypothesis非依存の記述であり、Positive/Negativeという
評価はHypothesisとの組み合わせでのみ意味を持つ、下記`EvidenceRelation`参照)。

`INSUFFICIENT_EVIDENCE`/`UNKNOWN`は正式な状態として扱い、無理にPositive/Negativeへ
分類しない。情報件数の多数決は禁止する(`lib.evidence.packet`参照)。

## Evidence Type

- FACT: 発生した事実そのもの(例: TDnetでの「会社予想を100億→120億へ修正」)。
- CLAIM: 主体が述べたことそのものはFACTだが、その内容(将来見通し等)の真偽は別
  (例: 会社IRの「需要は今後も堅調と考えている」)。
- INTERPRETATION: 二次情報源による解釈・要約(例: 新聞の「市場予想を上回る上方修正」)。
- OPINION: 個人・SNS等の見解(例: Xの「まだ全然織り込まれていない」)。
- IDEA: 投資アイデアの種(既存`lib.schemas.idea.Idea`と同種、Hypothesis化される前)。

`Hypothesis`はEvidence Typeに含めない(`lib.schemas.hypothesis.Hypothesis`という
既存の別schemaがあり、EvidenceそのものではなくEvidenceから導かれる仮説だから)。

## Raw / Normalized / Derived

`DataLayer`で区別する。AIが生成したDerived DataがRaw Factを上書きしてはならない
(`ai_derived_provenance`が設定されたレコードは`layer=DERIVED`のみ許可する)。
Raw -> Normalized -> Derivedのlineageは`lib.registry.provenance.ProvenanceStore`
(既存、Phase1.1〜)をそのまま再利用して追跡する(新しいProvenance機構は作らない)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from lib.sources.catalog import DataCapability, SourceMetadata


class EvidenceType(StrEnum):
    FACT = "FACT"
    CLAIM = "CLAIM"
    INTERPRETATION = "INTERPRETATION"
    OPINION = "OPINION"
    IDEA = "IDEA"


class DataLayer(StrEnum):
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    DERIVED = "DERIVED"


class EvidenceRelation(StrEnum):
    """Hypothesisが存在する場合のみ付与できる、Evidenceとの関係(Derived Relation)。

    Evidence自体にはこの値を保持しない(`EvidenceRecord`には無い)。
    `lib.evidence.packet.build_evidence_packet()`が、呼び出し側から明示的に
    与えられたHypothesis/ResearchQuestionとの関係として付与する
    (自動分類エンジンはPhase3Dでは実装しない、Schemaのみ)。
    """

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    ALTERNATIVE_EXPLANATION = "ALTERNATIVE_EXPLANATION"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class AvailabilityBasis(StrEnum):
    """`available_at`をどう決定したかの根拠(D0040)。

    `UNKNOWN`の場合、`available_at`にpublished_at等からの推測値を代入して
    誤魔化さない(呼び出し側が実際に確認できた値のみを使う。値が分からない場合は
    推測しない方針)。`RevisionHistory.as_of()`は既定で`UNKNOWN`のVersionを
    安全側(PIT利用不可)として除外する。
    """

    EXACT = "EXACT"  # 公式に確認された正確な時刻
    OBSERVED = "OBSERVED"  # 研究所側が実際に観測した時刻(retrieved_at等から確認)
    INFERRED = "INFERRED"  # 制度的なルール等から推定(例: 東証適時開示は15:00以降翌営業日扱い)
    UNKNOWN = "UNKNOWN"  # 不明(値を推測で埋めない)


class AvailabilitySemantics(StrEnum):
    """2種類のHistorical Researchを区別する(D0042)。

    A. Market Information Study: 「市場参加者がいつ情報を知り得たか」
       (`SourceMetadata.published_at`、market_public_at相当を基準にする)。
    B. Reproducible System Simulation: 「このResearch LabのData Pipelineでは
       いつ情報を取得できたか」(`SourceMetadata.available_at`、
       provider_available_at相当を基準にする)。

    両者を混同しない。市場には15:30に公開されたがJ-Quants Lightでは18:00まで
    取れなかった場合、市場反応研究(A)では15:30を使う可能性がある一方、
    「当時このシステムを運用していた」というSimulation(B)では18:00以前には
    使ってはならない。`lib.schemas.experiment.Experiment.availability_semantics`
    で、どちらの基準を使用したExperimentかを追跡可能にする。
    """

    MARKET_PUBLIC_AT = "MARKET_PUBLIC_AT"  # A系統
    PROVIDER_AVAILABLE_AT = "PROVIDER_AVAILABLE_AT"  # B系統(既定、このLabのBacktestは通常こちら)


class ValueAvailability(StrEnum):
    """Fundamental Metricの値そのものの状態(Stored Value State、D0043、
    Phase4A Fundamental Schema正式実装)。

    NULLを0へ変換しない、という契約を型で表現する。**As-of時点のTemporal
    Usability(問い合わせ時点でまだ利用できないという結果)とは別概念であり
    混同しない**: 後者はこの列挙型のメンバーとしては持たず、
    `lib.fundamentals.view.fundamentals_as_of()`が該当Seriesに`None`を返すことで
    表現する(Stored Value State = このMetricの値が実際どうだったか、
    Temporal Usability = decision_at時点でその値を参照してよかったか、は
    直交する別軸)。
    """

    PRESENT = "PRESENT"  # 値が存在し、正常にParseできた
    NOT_APPLICABLE = "NOT_APPLICABLE"  # 会計基準上、そもそも存在しない指標(0ではない)
    MISSING_OR_UNSPECIFIED = "MISSING_OR_UNSPECIFIED"  # Provider側で空だが、確定的な理由が無い(NOT_DISCLOSEDと決めつけない)
    UNKNOWN = "UNKNOWN"  # Parse不能等、値の状態そのものが判定できない


@dataclass(kw_only=True, frozen=True)
class AiDerivedProvenance:
    """AIが生成したDerived Record(要約・Event抽出・Entity Mapping・Hypothesis草案等)の
    再現性/比較可能性のためのProvenance(D0040)。"""

    model_provider: str
    model_name: str
    model_version: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    input_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    retrieval_plan_hash: str | None = None
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class SourceVersion:
    """Source Record 1件の、あるバージョン(Revision履歴の1エントリ、D0040)。

    決算の後日訂正・Macro統計のRevision・PDF差し替え・News更新等を表現する。
    `value`はこのVersion時点での値そのもの(文字列表現。数値・単位はドメイン側で解釈する)。
    """

    source_record_id: str
    source_version_id: str
    value: str
    available_at: datetime
    retrieved_at: datetime
    availability_basis: AvailabilityBasis = AvailabilityBasis.UNKNOWN
    supersedes_version_id: str | None = None
    is_correction: bool = False
    revision_reason: str | None = None  # 訂正理由(例: "会社側の入力ミス訂正"、任意)
    event_at: date | None = None  # 対象時点(value_date相当)
    published_at: datetime | None = None
    first_seen_at: datetime | None = None
    source_version_at: datetime | None = None  # Source側でこのVersionが発行された時刻

    def __post_init__(self) -> None:
        if self.available_at.tzinfo is None or self.retrieved_at.tzinfo is None:
            raise ValueError("available_at / retrieved_at はtz-awareである必要があります")
        if self.published_at is not None and self.published_at.tzinfo is None:
            raise ValueError("published_at はtz-awareである必要があります")


@dataclass(frozen=True)
class RevisionHistory:
    """1つのSource Record系列(series)についての、全Versionの履歴。"""

    series_id: str
    versions: tuple[SourceVersion, ...] = field(default_factory=tuple)

    def as_of(self, decision_at: datetime, *, include_unknown_availability: bool = False) -> SourceVersion | None:
        """decision_at時点で利用可能だった最新のVersionを返す(将来のRevisionをLeakしない)。

        `availability_basis=UNKNOWN`のVersionは既定で除外する(available_atを
        確認できていないものを「使えた」と扱わない、安全側デフォルト)。
        呼び出し側が明示的に許容する場合のみ`include_unknown_availability=True`とする。
        該当Versionが無ければ`None`(架空の値を返さない)。
        """
        if decision_at.tzinfo is None:
            raise ValueError("decision_at はtz-awareである必要があります")
        candidates = [
            v
            for v in self.versions
            if v.available_at <= decision_at
            and (include_unknown_availability or v.availability_basis != AvailabilityBasis.UNKNOWN)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.available_at)

    def latest(self) -> SourceVersion | None:
        """(PIT非考慮の)現在取得できる最新版。過去Decisionへ流用してはならない
        (`as_of()`を使うこと)。"""
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.available_at)


@dataclass(kw_only=True, frozen=True)
class EvidenceRecord:
    """研究所が扱うEvidence 1件(FACT/CLAIM/INTERPRETATION/OPINION/IDEAのいずれか)。

    Hypothesisに対するPositive/Negativeの評価は一切持たない(`EvidenceRelation`参照)。
    `is_usable_at()`でPITフィルタする(`source.available_at`基準)。

    `capability`は`lib.evidence.retrieval`がResearchQuestionの要求と突き合わせるための
    横断的分類(`DataCapability`)。`source.source_type`(例: "TDNET"/"EDINET"等、
    具体的なSource system名)とは別概念であり、文字列の一致に頼った推測はしない。
    """

    evidence_id: str
    evidence_type: EvidenceType
    layer: DataLayer
    capability: DataCapability
    content: str
    source: SourceMetadata
    value_date: date | None = None
    related_codes: tuple[str, ...] = field(default_factory=tuple)
    related_sectors: tuple[str, ...] = field(default_factory=tuple)
    ai_derived_provenance: AiDerivedProvenance | None = None
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if self.ai_derived_provenance is not None and self.layer != DataLayer.DERIVED:
            raise ValueError(
                f"evidence_id={self.evidence_id}: ai_derived_provenanceが設定されている場合、"
                "layerはDERIVEDである必要があります(AI生成DataがRaw/Normalizedを名乗ることを禁止する)"
            )

    def is_usable_at(self, decision_at: datetime) -> bool:
        if decision_at.tzinfo is None:
            raise ValueError("decision_at はtz-awareである必要があります")
        return self.source.available_at <= decision_at


def filter_usable_at(evidence: Sequence[EvidenceRecord], decision_at: datetime) -> tuple[EvidenceRecord, ...]:
    """decision_at時点で利用可能なEvidenceだけを返す(Look-ahead防止)。"""
    return tuple(e for e in evidence if e.is_usable_at(decision_at))
