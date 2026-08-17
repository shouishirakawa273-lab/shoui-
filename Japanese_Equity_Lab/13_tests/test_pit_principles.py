"""PIT Compliance Test Suite(Principle-derived、4A.5.1-1)。

## なぜこのFileが存在するか

D0049(Fundamentals)/D0050(Disclosures)は、`available_at`が`market_public_at`
へFallbackするという**同型のBug**が2つの独立したModuleに存在していたことを
明らかにした。さらにD0050では、既存Test(`test_tdnet_integration.py`)が
そのBugのある挙動をそのままAssertしており、`pytest`全体がPASSしていても
それがSemantic Correctnessを意味しないことも判明した(Research Engineering
Principle、`Test Pass != Semantic Correctness`、`DECISIONS.md` D0050参照)。

このFileは、個別Moduleの実装(`lib.fundamentals.evidence`/
`lib.disclosures.evidence`等)に付随したTestとは別に、**Architecture
Principleから直接期待値を導出したTest**だけを集める。実装Behaviorを
コピーしたTestは書かない(実装が誤っていれば、コピーしたTestも同じ誤りを
「正しい」とAssertしてしまうため)。

## Static Literal Pattern Testについて

このFile末尾の`test_defense_in_depth_*`Testは、特定の文字列Pattern
(例: `market_public_at`という語がAssertion中に現れるか)をGrepするだけの
Static Testであり、**Semantic Test(上記のPrinciple-derived Test)より
下位に位置づける**(2026-08-17実装Round、ユーザー指示)。単独のPrimary
Guaranteeとしては使わず、あくまでDefense-in-depthとして残す。

## 既存Testとの重複回避

Entity Registry(`test_entity_registry.py`)・古いPrice PIT層
(`test_point_in_time.py`)・Evidence層のFuture Injection単体
(`test_evidence_model.py`)には既に相応のCoverageがある。このFileでは
それらを機械的に再実装せず、**Principle-Suiteとしての代表テストを1本だけ
置き**(重複を最小化しつつ、このFileだけを見ればPIT原則の全体像が分かる
ようにする)、既存Coverageとの関係を各Testのdocstringに明記する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.view import disclosures_as_of
from lib.evidence.model import (
    AvailabilityBasis,
    AvailabilitySemantics,
    EvidenceRecord,
    RevisionHistory,
    SourceVersion,
    ValueAvailability,
)
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
from lib.sources.catalog import SourceAuthorityClass
from lib.sources.entity_registry import EntityIdentifierMapping, EntityRegistry, MappingConfidence

# --- 全Testで共通の時刻Scenario(D0049/D0050の実例、以後このFile内で再利用) ---

MARKET_PUBLIC_AT = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
RETRIEVED_AT = datetime(2026, 8, 17, 15, 6, tzinfo=UTC)
DECISION_AT_BETWEEN = datetime(2026, 8, 17, 15, 3, tzinfo=UTC)
DECISION_AT_BEFORE_PUBLIC = datetime(2026, 8, 17, 14, 59, tzinfo=UTC)


# --- Fundamentals/Disclosures共通のFixture Helper ---


def _build_fundamentals_evidence(*, market_public_at: datetime | None, retrieved_at: datetime) -> EvidenceRecord:
    envelope = DisclosureEnvelope(
        envelope_id="ENV_PIT_PRINCIPLE_1",
        provider_code="72030",
        internal_code="7203",
        disclosure_number="D_PRINCIPLE_1",
        document_type="FYFinancialStatements_Consolidated_IFRS",
        disclosure_date=market_public_at.date() if market_public_at is not None else None,
        disclosure_time=market_public_at.strftime("%H:%M") if market_public_at is not None else None,
        market_public_at=market_public_at,
        market_public_at_basis=(AvailabilityBasis.EXACT if market_public_at is not None else AvailabilityBasis.UNKNOWN),
        retrieved_at=retrieved_at,
    )
    metric = FundamentalMetric(
        metric_id="MET_PIT_PRINCIPLE_1",
        envelope_id=envelope.envelope_id,
        series_id="7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS",
        metric_type="operating_profit_current_year_forecast",
        raw_value="120",
        value=Decimal("120"),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.COMPANY_FORECAST,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="FOP",
    )
    return disclosure_metric_to_evidence(envelope, metric)


def _build_disclosures_evidence(*, market_public_at: datetime | None, retrieved_at: datetime) -> EvidenceRecord:
    document = DisclosureDocument(
        internal_document_id="DOC_PIT_PRINCIPLE_1",
        source_document_id="D1",
        entity_id="7203",
        title="決算短信〔IFRS〕(連結)",
        originating_source="TDnet",
        delivery_provider="J-Quants",
        market_public_at=market_public_at,
        market_public_at_basis=(AvailabilityBasis.EXACT if market_public_at is not None else AvailabilityBasis.UNKNOWN),
        retrieved_at=retrieved_at,
    )
    return disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)


# Module横断でPrincipleを検証するための登録リスト。将来3つ目のEvidence生成
# Moduleが増えた場合は、ここへ1行追加するだけでPIT-P02/PIT-P05のParametrize
# 対象へ自動的に含まれる(拡張性のための構造、ユーザー指示PIT-P02参照)。
_EVIDENCE_BUILDERS: tuple[tuple[str, object], ...] = (
    ("fundamentals", _build_fundamentals_evidence),
    ("disclosures", _build_disclosures_evidence),
)


# ============================================================
# PIT-P01: Unknown Provider Availability
# ============================================================


@pytest.mark.parametrize("name,builder", _EVIDENCE_BUILDERS)
def test_pit_p01_unusable_between_market_public_at_and_retrieved_at(name: str, builder: object) -> None:
    """market_public_at=15:00、provider availability=UNKNOWN、retrieved_at=15:06
    のとき、decision_at=15:03(15:00と15:06の間)ではEvidenceが利用不可能で
    あること(D0049/D0050の実例そのもの)。"""
    evidence = builder(market_public_at=MARKET_PUBLIC_AT, retrieved_at=RETRIEVED_AT)  # type: ignore[operator]
    assert evidence.is_usable_at(DECISION_AT_BETWEEN) is False, name


@pytest.mark.parametrize("name,builder", _EVIDENCE_BUILDERS)
def test_pit_p01_usable_at_retrieved_at(name: str, builder: object) -> None:
    """同じScenarioで、decision_at=15:06(retrieved_atと一致)では利用可能に
    なること。decision_at=14:59(market_public_atより前)では利用不可能の
    ままであること。"""
    evidence = builder(market_public_at=MARKET_PUBLIC_AT, retrieved_at=RETRIEVED_AT)  # type: ignore[operator]
    assert evidence.is_usable_at(RETRIEVED_AT) is True, name
    assert evidence.is_usable_at(DECISION_AT_BEFORE_PUBLIC) is False, name


# ============================================================
# PIT-P02: Cross-module Semantic Consistency
# ============================================================


@pytest.mark.parametrize("name,builder", _EVIDENCE_BUILDERS)
def test_pit_p02_available_at_equals_retrieved_at_never_market_public_at(name: str, builder: object) -> None:
    """D0049とD0050は独立したModuleで発生した同型のBugだった。次に3つ目の
    Evidence生成Moduleが増えても同じ保証が要求されるよう、`_EVIDENCE_
    BUILDERS`に登録済みの全Moduleへ同一Parametrizeを適用する。"""
    evidence = builder(market_public_at=MARKET_PUBLIC_AT, retrieved_at=RETRIEVED_AT)  # type: ignore[operator]
    assert evidence.source.available_at == RETRIEVED_AT, name
    assert evidence.source.available_at != MARKET_PUBLIC_AT, name
    assert evidence.source.published_at == MARKET_PUBLIC_AT, name


# ============================================================
# PIT-P03: Valid Visibility Separation(A系統/B系統の非同一視)
# ============================================================


def test_pit_p03_market_public_at_and_provider_availability_are_not_interchangeable() -> None:
    """market_public_at(A系統、市場情報研究)とprovider/system availability
    (B系統、再現可能System Simulation)は同一視しない。同じdecision_at
    (15:03)に対して、A系統(`disclosures_as_of(..., MARKET_PUBLIC_AT)`)と
    B系統(`EvidenceRecord.is_usable_at`)が異なる可視性判定を返しうることを
    直接確認する。"""
    document = DisclosureDocument(
        internal_document_id="DOC_PIT_P03",
        source_document_id="D_P03",
        entity_id="7203",
        title="決算短信〔IFRS〕(連結)",
        market_public_at=MARKET_PUBLIC_AT,
        market_public_at_basis=AvailabilityBasis.EXACT,
        retrieved_at=RETRIEVED_AT,
    )
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)

    # A系統: market_public_at(15:00)は decision_at(15:03)以前なので可視。
    visible_a = disclosures_as_of([document], DECISION_AT_BETWEEN, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    assert document in visible_a

    # B系統: available_at(=retrieved_at=15:06)は decision_at(15:03)より後なので不可視。
    assert evidence.is_usable_at(DECISION_AT_BETWEEN) is False

    # 同じEvidenceについて、A系統は「見えた」B系統は「見えない」という
    # 分岐そのものがPrincipleの核心(D0042)。
    assert visible_a and not evidence.is_usable_at(DECISION_AT_BETWEEN)


# ============================================================
# PIT-P04: Invalid / suspicious temporal order
#   (Global Constructor Ruleにはしない、意味が確定しているScenarioのみ)
# ============================================================


def test_pit_p04_evidence_layer_construction_does_not_enforce_ordering_by_design_this_round() -> None:
    """`available_at >= published_at`をこのRoundではGlobal Constructor Rule
    として追加しない(Source semanticsを無視した巨大Invariantを追加しない、
    ユーザー2026-08-17実装Round指示)。このTestは「現状のCode Behaviorが
    まだ拒否しない」ことを記録するTripwireである(修正ではない)。

    唯一、意味が確定している既存Scenario(`lib.point_in_time.
    PointInTimeRecord`、旧Price PIT層)は既に`available_at < published_at`
    をConstructor Levelで拒否しており、これは`test_point_in_time.py::
    test_available_at_before_published_at_is_rejected`で既にTest済みの
    ため、このFileでは重複させない。Evidence層(`SourceMetadata`/
    `SourceVersion`/`DisclosureDocument`)はSource横断(TDnet/EDINET/
    Fundamentals)であり、`available_at`が`published_at`より早いことが
    構造的に正当なSourceが将来存在しないとは断定できないため、意味は
    まだ確定していない(次Round開始時にUserへ確認するOpen Questionとして
    `PHASE4A5_1_PLAN.md`に記録済み)。"""
    suspicious_published_at = datetime(2026, 8, 17, 15, 0, tzinfo=UTC)
    suspicious_available_at = datetime(2026, 8, 17, 14, 0, tzinfo=UTC)  # published_atより前

    # 現状、例外を出さず構築が成功する(Tripwire: これが将来Failし始めたら
    # Constructor Validationが追加されたことを意味し、DECISIONS.mdへの
    # 記録が必要というシグナルになる)。
    version = SourceVersion(
        source_record_id="SR_P04",
        source_version_id="V1",
        value="120",
        available_at=suspicious_available_at,
        retrieved_at=RETRIEVED_AT,
        published_at=suspicious_published_at,
    )
    assert version.available_at < version.published_at  # type: ignore[operator]


# ============================================================
# PIT-P05: Future Injection
# ============================================================


@pytest.mark.parametrize("name,builder", _EVIDENCE_BUILDERS)
def test_pit_p05_future_evidence_not_usable_before_its_available_at(name: str, builder: object) -> None:
    """未来のEvidence(available_atがdecision_atより後)は、実Pipelineを通した
    場合にもFilterされること。`test_evidence_model.py::test_filter_usable_
    at_excludes_future_evidence`は合成EvidenceRecordを直接構築して同じ
    Principleを検証しているが、このTestは実際のFundamentals/Disclosures
    構築経路(`disclosure_metric_to_evidence`/`disclosure_document_to_
    evidence`)を通した場合にも同じ保証が成り立つことを確認する(合成
    Recordだけでなく実Pipeline経由でも同じ、という点で重複ではない)。"""
    far_future_retrieved_at = datetime(2030, 1, 1, tzinfo=UTC)
    evidence = builder(market_public_at=None, retrieved_at=far_future_retrieved_at)  # type: ignore[operator]

    assert evidence.is_usable_at(RETRIEVED_AT) is False, name  # 現在時点ではまだ利用不可
    assert evidence.is_usable_at(far_future_retrieved_at) is True, name  # その時点以降は利用可能


# ============================================================
# PIT-P06: UNKNOWN Fallback Attack
# ============================================================


def test_pit_p06_unknown_basis_excluded_by_default_across_fundamentals_and_disclosures() -> None:
    """`AvailabilityBasis.UNKNOWN`は、Fundamentals(`RevisionHistory.as_of`)
    とDisclosures(`disclosures_as_of`)の両方で、既定(`include_unknown_
    availability=False`)では除外されること — UNKNOWNをFalse/0/最も早い
    Timestampへ暗黙変換しない、という原則を2つのModuleで**同時に**確認する
    (個別Moduleの既存Testはそれぞれ単独で確認しているが、両方を1つの
    Testで並べて確認するのはこのFileが初めて)。"""
    # Fundamentals側: RevisionHistory.as_of
    unknown_version = SourceVersion(
        source_record_id="SR_P06",
        source_version_id="V1",
        value="120",
        available_at=MARKET_PUBLIC_AT,
        retrieved_at=RETRIEVED_AT,
        availability_basis=AvailabilityBasis.UNKNOWN,
    )
    history = RevisionHistory(series_id="SERIES_P06", versions=(unknown_version,))
    assert history.as_of(RETRIEVED_AT) is None  # UNKNOWNは既定で見えない
    assert history.as_of(RETRIEVED_AT, include_unknown_availability=True) is unknown_version  # 明示時のみ見える

    # Disclosures側: disclosures_as_of
    document = DisclosureDocument(
        internal_document_id="DOC_P06",
        source_document_id="D_P06",
        title="決算短信〔IFRS〕(連結)",
        market_public_at=MARKET_PUBLIC_AT,
        market_public_at_basis=AvailabilityBasis.UNKNOWN,
        retrieved_at=RETRIEVED_AT,
    )
    visible_default = disclosures_as_of([document], RETRIEVED_AT, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    assert document not in visible_default  # UNKNOWNは既定で見えない
    visible_explicit = disclosures_as_of(
        [document],
        RETRIEVED_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        include_unknown_availability=True,
    )
    assert document in visible_explicit  # 明示時のみ見える


def test_pit_p06_value_availability_unknown_is_not_falsy_or_equal_to_present() -> None:
    """`ValueAvailability.UNKNOWN`がPythonの真偽値・他Memberと暗黙に等価
    扱いされないこと(`StrEnum`は文字列比較になるため、意図せず`==0`や
    `==False`にならないことを直接確認する)。"""
    assert bool(ValueAvailability.UNKNOWN) is True  # 空文字列ではないため常にTruthy
    assert ValueAvailability.UNKNOWN != ValueAvailability.PRESENT
    assert ValueAvailability.UNKNOWN != ValueAvailability.NOT_APPLICABLE
    assert ValueAvailability.UNKNOWN != 0
    assert ValueAvailability.UNKNOWN != False  # noqa: E712  意図的な明示比較


# ============================================================
# PIT-P07: Current State Leakage
# ============================================================


def test_pit_p07_entity_registry_as_of_does_not_leak_current_mapping_into_past_decision() -> None:
    """Current-onlyの識別子対応付けが、過去のdecision_atへ混入しないこと。

    詳細なMechanics(重複検知・Provider別識別子等)は`test_entity_
    registry.py`が既に広く確認済みであり、ここではそれを再実装しない。
    このTestは、このFile(Principle-derived Suite)自体がPIT-P07という
    原則を代表する1本を持つための、意図的な最小限の重複である(黙って
    省略せず、ここに明記する)。"""
    old_mapping = EntityIdentifierMapping(
        issuer_id="ISSUER_7203",
        canonical_name="OLD_NAME_CO",
        provider_identifiers={"jquants": "OLD_CODE"},
        valid_from=date(2020, 1, 1),
        valid_until=date(2026, 1, 1),
        mapping_confidence=MappingConfidence.HIGH,
    )
    new_mapping = EntityIdentifierMapping(
        issuer_id="ISSUER_7203",
        canonical_name="NEW_NAME_CO",
        provider_identifiers={"jquants": "NEW_CODE"},
        valid_from=date(2026, 1, 1),
        valid_until=None,
        mapping_confidence=MappingConfidence.HIGH,
    )
    registry = EntityRegistry([old_mapping, new_mapping])

    # 2025年時点(過去)のDecisionでは、2026年以降にしか有効でないNEW_CODEは見えない。
    past_decision = date(2025, 6, 1)
    assert registry.resolve(provider_name="jquants", provider_identifier="NEW_CODE", as_of=past_decision) is None
    resolved_old = registry.resolve(provider_name="jquants", provider_identifier="OLD_CODE", as_of=past_decision)
    assert resolved_old is not None
    assert resolved_old.canonical_name == "OLD_NAME_CO"

    # 現在(2026年以降)は逆に、失効済みのOLD_CODEは見えない。
    current_decision = date(2026, 6, 1)
    assert registry.resolve(provider_name="jquants", provider_identifier="OLD_CODE", as_of=current_decision) is None
    resolved_new = registry.resolve(provider_name="jquants", provider_identifier="NEW_CODE", as_of=current_decision)
    assert resolved_new is not None
    assert resolved_new.canonical_name == "NEW_NAME_CO"


# ============================================================
# Defense-in-depth(Static/Structural、Semantic Testより下位)
# ============================================================

_LAB_ROOT = Path(__file__).resolve().parent.parent

# T8 (訂正版): D0049 §5-1で意図的に固定した既知Guarded Gapの回帰Testは、
# `available_at == market_public_at`という文字列Patternに一致するが
# Bugではない。単純な「一致件数0」判定では偽陽性になるため、明示的に
# 除外する(前Round pit-auditor Reviewで判明、DECISIONS.md D0051 追記)。
_KNOWN_GUARDED_GAP_ALLOWLIST = frozenset(
    {
        "test_include_unknown_availability_true_reproduces_market_public_at_anchor_as_documented_gap",
    }
)


def test_defense_in_depth_no_test_asserts_the_pre_fix_bug_pattern_outside_allowlist() -> None:
    """D0049/D0050のBugそのものの形(`available_at == market_public_at`
    相当のAssertion)を持つTestが、既知のAllowlist外に存在しないことを
    構造確認する(Static、Semantic Test群の補完)。"""
    test_dir = _LAB_ROOT / "13_tests"
    violations: list[str] = []
    for path in sorted(test_dir.glob("test_*.py")):
        if path.name == "test_pit_principles.py":
            continue  # 自Fileの docstring/コメント自体がPatternを含みうるため除外
        text = path.read_text(encoding="utf-8")
        if "available_at == " not in text:
            continue
        if "market_public_at" not in text:
            continue
        # 疑わしいFileはFunction単位で確認し、Allowlist外の一致のみ報告する。
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "available_at ==" in line and "market_public_at" in line:
                # 直前50行以内にAllowlist登録済みFunction名があるかを確認する
                # (厳密なAST解析ではなく行ベースの近傍探索、既存test_edinet_
                # zip_canonicalize.pyの構造Testと同様の粒度)。
                window_start = max(0, line_no - 50)
                window = "\n".join(text.splitlines()[window_start:line_no])
                if any(name in window for name in _KNOWN_GUARDED_GAP_ALLOWLIST):
                    continue
                violations.append(f"{path.name}:{line_no}: {line.strip()}")
    assert not violations, f"D0049/D0050のBugの形をAssertする未Allowlist Testが見つかりました: {violations}"


def test_defense_in_depth_provider_normalizer_files_never_construct_document_relationship() -> None:
    """Raw Hash不一致だけを根拠に`DocumentRelationship`/`DuplicateRelationKind`
    を構築するコードが、Source固有Adapter/Normalizer全体
    (`lib/disclosures/providers/`配下)に存在しないことを確認する
    (既存`test_edinet_zip_canonicalize.py::test_edinet_zip_module_never_
    constructs_document_relationship`はedinet_zip.py単体のみが対象だった
    ため、T9としてLab全体のProvider層へ一般化する)。"""
    providers_dir = _LAB_ROOT / "lib" / "disclosures" / "providers"
    offenders: list[str] = []
    for path in sorted(providers_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "DocumentRelationship" in text or "DuplicateRelationKind" in text:
            offenders.append(path.name)
    assert not offenders, (
        f"Source固有Adapter/NormalizerがDocumentRelationship/DuplicateRelationKindを"
        f"参照しています(Raw Hash比較からRevision概念を自動構築していないか確認要): {offenders}"
    )


def test_defense_in_depth_availability_basis_fields_default_to_unknown_not_exact() -> None:
    """Schema内の`*_basis: AvailabilityBasis`型Fieldの既定値が、全て
    `AvailabilityBasis.UNKNOWN`であって`EXACT`ではないことを構造確認する
    (将来Field追加時に既定を安全側以外へ設定してしまう回帰を防ぐ)。"""
    import dataclasses

    from lib.disclosures.model import DisclosureDocument as _DD
    from lib.evidence.model import SourceVersion as _SV

    for cls in (_SV, _DD):
        for f in dataclasses.fields(cls):
            if f.name.endswith("_basis") and f.type in ("AvailabilityBasis", AvailabilityBasis):
                assert f.default == AvailabilityBasis.UNKNOWN, f"{cls.__name__}.{f.name} の既定値がUNKNOWNではありません"
