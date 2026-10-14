"""Macro Event & Surprise Foundation: Core Record Types(D0110.1)。

**MACRO MEASUREMENT FIRST. MACRO FORECASTING LATER.** 本Moduleは
「何のMacro Eventがいつ予定され、市場Consensusは事前にどうだったか、
最初に何が発表されたか、Surpriseはどう計算されるか」をPIT-correctに
記録するだけであり、CPI/FOMC/FX/Rates/Commoditiesの予測・解釈・
投資判断は一切行わない(D0110.1 §21/§23)。

## 既存`lib/macro/`との関係(複製しない、衝突しない)

既存`lib.macro.model.MacroRecord`(Phase4D)はSeries中心のLong-form
Macro Observation(CPI/GDP/失業率等の連続Series、`RevisionHistory`
によるVintage管理)であり、本Moduleとは目的・形状が異なる——
`RevisionHistory.as_of()`は「ある時点で見えていた最新Version」を返す
設計であり、「史上最初のRelease(Never Overwrite)」という本Module
の中心要件(D0110.1 §10)とは意味的に衝突する。本Moduleは**Event
中心**(1つの予定されたEvent発生に対するConsensus/First Release/
Surpriseの組)という別の形状のため、新しいNamespace(`lib/macro_
events/`)として独立させ、既存`lib/macro/`は一切変更しない。

## 4つの別概念(D0110.1 §4、1つの可変Objectへ潰さない)

`MacroEvent`(予定されたEvent発生)→ `MacroConsensusSnapshot`(0件以上、
Snapshot時点ごとに別Record)/ `MacroFirstRelease`(最初の発表、Later
Revisionで上書きしない)→ `MacroSurprise`(`lib.macro_events.surprise`、
特定のConsensus Snapshot + First Releaseの組から計算)。

## Event Type Vocabulary(v1 Scope: CPI + FOMCのみ)

Repository既存規約(`FundamentalMetric.metric_type`・`PredictionRecord.
target`等)と同じく、Event Type/Dimension名は固定Enumではなく自由
文字列とし、v1でSupportするEvent Typeのみ`SUPPORTED_EVENT_TYPES`
Frozensetで宣言する(未対応Type要求時は`UNSUPPORTED_EVENT_TYPE`で
明示的にFail Closedする、D0110.1 §3)。

## Tamper Evidence(既存D0107 Hashパターンの再利用)

既存`lib.evaluation.integrity.compute_record_hash()`をそのまま再利用
する(新しいHash Algorithmは作らない、D0110.1 §20)。各`build_*()`
関数が構築時に1度だけHashを計算し、以降Recordは`frozen=True`により
不変。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lib.evaluation.integrity import compute_record_hash

EVENT_TYPE_CPI = "CPI"
EVENT_TYPE_FOMC = "FOMC"
SUPPORTED_EVENT_TYPES: frozenset[str] = frozenset({EVENT_TYPE_CPI, EVENT_TYPE_FOMC})

# Dimension Vocabulary(D0110.1 §12、推奨値のみ——自由文字列、強制しない)
DIMENSION_CPI_HEADLINE_MOM = "HEADLINE_MOM"
DIMENSION_CPI_HEADLINE_YOY = "HEADLINE_YOY"
DIMENSION_CPI_CORE_MOM = "CORE_MOM"
DIMENSION_CPI_CORE_YOY = "CORE_YOY"
DIMENSION_FOMC_POLICY_RATE_TARGET = "POLICY_RATE_TARGET"
DIMENSION_FOMC_POLICY_RATE_MIDPOINT = "POLICY_RATE_MIDPOINT"
DIMENSION_FOMC_DOT_MEDIAN = "DOT_MEDIAN"
DIMENSION_FOMC_GDP_PROJECTION = "GDP_PROJECTION"
DIMENSION_FOMC_INFLATION_PROJECTION = "INFLATION_PROJECTION"
DIMENSION_FOMC_UNEMPLOYMENT_PROJECTION = "UNEMPLOYMENT_PROJECTION"

# Unit Vocabulary(D0110.1 §17、Percent/Percentage Point/Basis Point/Index Pointを混同しない)
UNIT_PERCENT = "PERCENT"
UNIT_PERCENTAGE_POINT = "PERCENTAGE_POINT"
UNIT_BASIS_POINT = "BASIS_POINT"
UNIT_INDEX_POINT = "INDEX_POINT"


class MacroEventSchemaError(ValueError):
    """本Module固有のSchema/Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する(D0103-D0110と同じ方針)。PIT違反・
    Domain-level計算失敗は`lib.macro_events.surprise`のTyped Outcome
    (`MacroSurpriseStatus`)で表現し、本Errorとは区別する。"""


def require_nonempty_str(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise MacroEventSchemaError(f"{label} は空でないstrである必要があります")


def require_tz_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None:
        raise MacroEventSchemaError(f"{label} はtz-awareである必要があります")


def require_decimal(value: object, *, label: str) -> None:
    if not isinstance(value, Decimal):
        raise MacroEventSchemaError(f"{label} は Decimal である必要があります(実際: {type(value).__name__})")


@dataclass(kw_only=True, frozen=True)
class MacroEvent:
    """1つの予定されたMacro Event発生(D0110.1 §5)。

    `event_id`は歴史的に一意で具体的なIdentifierである必要がある
    (例: `"US_CPI_2026_09"`・`"FOMC_2026_09_16"`)——`"LATEST_CPI"`
    のような曖昧なIDは使わない(本Dataclass自体は文字列内容の妥当性を
    強制しないが、Docstring/Convention上の要件として明記する)。

    `scheduled_at`(予定時刻)と`schedule_available_at`(その予定情報
    自体がいつ判明したか、PIT)は別軸——Eventが延期される可能性がある
    ため、実際の発表時刻は`MacroFirstRelease.actual_public_at`が持つ
    (D0110.1 §6)。`event_version`は予定の改訂(延期等)を新しい
    Immutable Snapshotとして表現する——既存Recordを書き換えない
    (D0110.1 §6、汎用Scheduling Systemは作らない)。
    """

    event_id: str
    event_type: str
    jurisdiction: str
    scheduled_at: datetime
    event_period: str
    source_id: str
    schedule_available_at: datetime
    event_version: int
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("event_type", self.event_type),
            ("jurisdiction", self.jurisdiction),
            ("event_period", self.event_period),
            ("source_id", self.source_id),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.scheduled_at, label="scheduled_at")
        require_tz_aware(self.schedule_available_at, label="schedule_available_at")
        require_tz_aware(self.created_at, label="created_at")
        if self.event_version < 1:
            raise MacroEventSchemaError(f"event_version は1以上である必要があります(実際: {self.event_version})")


def build_macro_event(
    *,
    event_id: str,
    event_type: str,
    jurisdiction: str,
    scheduled_at: datetime,
    event_period: str,
    source_id: str,
    schedule_available_at: datetime,
    created_at: datetime,
    event_version: int = 1,
) -> MacroEvent:
    """`MacroEvent`を構築する唯一のEntrypoint(D0110.1 §5)。

    `event_type`が`SUPPORTED_EVENT_TYPES`(v1はCPI/FOMCのみ)に属さ
    ない場合は構築時点で明示的に拒否する(Caller側のProgramming
    Errorに相当するため、Typed Statusではなく`MacroEventSchemaError`
    を使う——D0110.1 §3「v1 must support only CPI/FOMC」)。
    """
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise MacroEventSchemaError(
            f"event_type={event_type!r} は未対応です(SUPPORTED_EVENT_TYPES={sorted(SUPPORTED_EVENT_TYPES)})"
        )
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "jurisdiction": jurisdiction,
        "scheduled_at": scheduled_at,
        "event_period": event_period,
        "source_id": source_id,
        "schedule_available_at": schedule_available_at,
        "event_version": event_version,
        "created_at": created_at,
    }
    return MacroEvent(
        event_id=event_id,
        event_type=event_type,
        jurisdiction=jurisdiction,
        scheduled_at=scheduled_at,
        event_period=event_period,
        source_id=source_id,
        schedule_available_at=schedule_available_at,
        event_version=event_version,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class MacroConsensusSnapshot:
    """特定時点で観測された市場Consensus(D0110.1 §7)。

    `"Consensus = 3.0%"`では不十分——`consensus_snapshot_at`(観測
    時点)を常に伴う。同じEvent/Dimensionについて複数のSnapshotが
    存在してよく、新しいSnapshotが古いSnapshotを上書きすることは
    一切ない(別々の`consensus_snapshot_id`を持つ別Record、D0110.1
    §7「Never overwrite the earlier snapshot」)。
    """

    consensus_snapshot_id: str
    event_id: str
    dimension: str
    value: Decimal
    unit: str
    consensus_snapshot_at: datetime
    available_at: datetime
    provider: str
    source_id: str
    provider_version: str | None
    estimate_count: int | None
    dispersion: Decimal | None
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("consensus_snapshot_id", self.consensus_snapshot_id),
            ("event_id", self.event_id),
            ("dimension", self.dimension),
            ("unit", self.unit),
            ("provider", self.provider),
            ("source_id", self.source_id),
        ):
            require_nonempty_str(value, label=name)
        require_decimal(self.value, label="MacroConsensusSnapshot.value")
        require_tz_aware(self.consensus_snapshot_at, label="consensus_snapshot_at")
        require_tz_aware(self.available_at, label="available_at")
        require_tz_aware(self.created_at, label="created_at")
        if self.estimate_count is not None and self.estimate_count < 0:
            raise MacroEventSchemaError("estimate_count は0以上である必要があります")
        if self.dispersion is not None:
            require_decimal(self.dispersion, label="MacroConsensusSnapshot.dispersion")


def build_macro_consensus_snapshot(
    *,
    consensus_snapshot_id: str,
    event_id: str,
    dimension: str,
    value: Decimal,
    unit: str,
    consensus_snapshot_at: datetime,
    available_at: datetime,
    provider: str,
    source_id: str,
    created_at: datetime,
    provider_version: str | None = None,
    estimate_count: int | None = None,
    dispersion: Decimal | None = None,
) -> MacroConsensusSnapshot:
    """`MacroConsensusSnapshot`を構築する唯一のEntrypoint(D0110.1 §7)。
    呼び出し側が明示的な`consensus_snapshot_id`/`consensus_snapshot_at`
    を渡すたびに新しいImmutable Recordが1件増えるのみであり、既存
    Snapshotの上書き経路はどこにも存在しない(D0110.1 §9、Silent
    Latest-Consensus Selectionも行わない)。
    """
    payload = {
        "consensus_snapshot_id": consensus_snapshot_id,
        "event_id": event_id,
        "dimension": dimension,
        "value": value,
        "unit": unit,
        "consensus_snapshot_at": consensus_snapshot_at,
        "available_at": available_at,
        "provider": provider,
        "source_id": source_id,
        "provider_version": provider_version,
        "estimate_count": estimate_count,
        "dispersion": dispersion,
        "created_at": created_at,
    }
    return MacroConsensusSnapshot(
        consensus_snapshot_id=consensus_snapshot_id,
        event_id=event_id,
        dimension=dimension,
        value=value,
        unit=unit,
        consensus_snapshot_at=consensus_snapshot_at,
        available_at=available_at,
        provider=provider,
        source_id=source_id,
        provider_version=provider_version,
        estimate_count=estimate_count,
        dispersion=dispersion,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class MacroFirstRelease:
    """Eventで最初に発表された値(D0110.1 §10)。

    `actual_first_release`は**史上最初に公表された値**であり、後の
    改訂値(Revised Actual)ではない——後からのRevisionを理由に本
    Recordを書き換えることは一切ない(別途将来のPhaseでRevision
    専用Recordを追加する余地のみ残す、D0110.1 §10/§11)。
    `previous_as_published`も同様に、この発表時点で表示されていた
    「前回値」をそのまま保持し、後の遡及改定後の値へ差し替えない
    (D0110.1 §11)。
    """

    release_id: str
    event_id: str
    dimension: str
    actual_first_release: Decimal
    previous_as_published: Decimal | None
    unit: str
    actual_public_at: datetime
    available_at: datetime
    source_id: str
    source_version: str | None
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("release_id", self.release_id),
            ("event_id", self.event_id),
            ("dimension", self.dimension),
            ("unit", self.unit),
            ("source_id", self.source_id),
        ):
            require_nonempty_str(value, label=name)
        require_decimal(self.actual_first_release, label="MacroFirstRelease.actual_first_release")
        if self.previous_as_published is not None:
            require_decimal(self.previous_as_published, label="MacroFirstRelease.previous_as_published")
        require_tz_aware(self.actual_public_at, label="actual_public_at")
        require_tz_aware(self.available_at, label="available_at")
        require_tz_aware(self.created_at, label="created_at")


def build_macro_first_release(
    *,
    release_id: str,
    event_id: str,
    dimension: str,
    actual_first_release: Decimal,
    unit: str,
    actual_public_at: datetime,
    available_at: datetime,
    source_id: str,
    created_at: datetime,
    previous_as_published: Decimal | None = None,
    source_version: str | None = None,
) -> MacroFirstRelease:
    """`MacroFirstRelease`を構築する唯一のEntrypoint(D0110.1 §10)。
    本関数には`update`/`revise`相当のMethodが存在しない——後から
    改訂値が得られた場合は、新しい(別の)`release_id`を持つ将来の
    Revision専用Record(本Roundでは作らない)として表現すること。
    """
    payload = {
        "release_id": release_id,
        "event_id": event_id,
        "dimension": dimension,
        "actual_first_release": actual_first_release,
        "previous_as_published": previous_as_published,
        "unit": unit,
        "actual_public_at": actual_public_at,
        "available_at": available_at,
        "source_id": source_id,
        "source_version": source_version,
        "created_at": created_at,
    }
    return MacroFirstRelease(
        release_id=release_id,
        event_id=event_id,
        dimension=dimension,
        actual_first_release=actual_first_release,
        previous_as_published=previous_as_published,
        unit=unit,
        actual_public_at=actual_public_at,
        available_at=available_at,
        source_id=source_id,
        source_version=source_version,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


__all__ = [
    "DIMENSION_CPI_CORE_MOM",
    "DIMENSION_CPI_CORE_YOY",
    "DIMENSION_CPI_HEADLINE_MOM",
    "DIMENSION_CPI_HEADLINE_YOY",
    "DIMENSION_FOMC_DOT_MEDIAN",
    "DIMENSION_FOMC_GDP_PROJECTION",
    "DIMENSION_FOMC_INFLATION_PROJECTION",
    "DIMENSION_FOMC_POLICY_RATE_MIDPOINT",
    "DIMENSION_FOMC_POLICY_RATE_TARGET",
    "DIMENSION_FOMC_UNEMPLOYMENT_PROJECTION",
    "EVENT_TYPE_CPI",
    "EVENT_TYPE_FOMC",
    "SUPPORTED_EVENT_TYPES",
    "UNIT_BASIS_POINT",
    "UNIT_INDEX_POINT",
    "UNIT_PERCENT",
    "UNIT_PERCENTAGE_POINT",
    "MacroConsensusSnapshot",
    "MacroEvent",
    "MacroEventSchemaError",
    "MacroFirstRelease",
    "build_macro_consensus_snapshot",
    "build_macro_event",
    "build_macro_first_release",
    "require_decimal",
    "require_nonempty_str",
    "require_tz_aware",
]
