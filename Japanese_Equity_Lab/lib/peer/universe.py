"""PIT-Safe Peer Candidate Universe解決(Stage 3.17、D0095)。

First Eligibility Layer(要件v1 §7): 公式Classification(既定では東証33
業種区分、`S33`)の一致のみでCandidateを生成する。**この一致だけでは
最終的な経済的比較可能性を意味しない**——Comparability Guard
(`lib.peer.comparability`)を経由して初めて`AcceptedPeer`になる。

## Field名について(重要、Provenance明示)

`lib.data_sources.convert.equities_master_payload_to_listing_records()`
は`Sector33Code`/`CompanyName`という未検証のField名を仮定しているが
(同Module Docstring「この推論はMain Claudeによる妥当な補完」参照)、
D0094/D0095で実際にLocal Snapshot(`01_data/raw/local_snapshot_input/
equities_master.json`)を実測した結果、実際のField名は`S33`(業種
コード)・`S33Nm`(業種名)・`CoNameEn`(英語社名)・`Code`(Provider
Code)・`Date`(このMaster Snapshot自身の基準日)であることを確認した。
このModuleは実測済みのField名を既定値として使う(推測ではなく実データ
確認済み、ただし呼び出し側がField名を明示的に上書きできるようにし、
将来Provider仕様が変わった場合にも対応できるようにする)。**既存
`equities_master_payload_to_listing_records()`は変更しない**(Stage
3.17のScope外、既存Test Contractへの影響を避けるため独立Readerとして
実装する)。

## PIT-Safety(要件v1 §6、最重要)

Local Snapshotの`equities_master.json`は単一時点のSnapshotであり
(`Date`Fieldが示す基準日は2026-08-17、確認済み)、Historical Sector
Classificationを持たない。したがってResearch as_ofとSnapshot基準日が
一致しない限り、「as_of時点で本当にこの業種区分だったか」は証明できない
——今日の分類をas_ofへ無条件に遡らせない(Silent Backward Projection
禁止)。`classification_snapshot_as_of != as_of.date()`の場合は
`UniverseResolution.PARTIAL`とし、その理由を`pit_note`へ明示する
(`lib.universe.ListingBasedUniverseProvider`のSurvivorship Bias
Handlingと同じ設計思想)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from lib.data_sources.ticker_codes import TickerCodeNormalizationError, normalize_provider_code_to_internal
from lib.peer.model import CLASSIFICATION_SYSTEM_TSE_SECTOR_33, PeerCandidate, PeerUniverseSnapshot
from lib.universe import UniverseResolution

_DEFAULT_CODE_FIELD = "Code"
_DEFAULT_CLASSIFICATION_FIELD = "S33"
_DEFAULT_COMPANY_NAME_FIELD = "CoNameEn"
_DEFAULT_SNAPSHOT_DATE_FIELD = "Date"


def _extract_str(row: Mapping[str, object], field_name: str) -> str | None:
    value = row.get(field_name)
    if value is None or value == "":
        return None
    return str(value)


def resolve_peer_candidate_universe(
    *,
    target_entity_code: str,
    as_of: datetime,
    classification_rows: Sequence[Mapping[str, object]],
    classification_system: str = CLASSIFICATION_SYSTEM_TSE_SECTOR_33,
    code_field: str = _DEFAULT_CODE_FIELD,
    classification_field: str = _DEFAULT_CLASSIFICATION_FIELD,
    company_name_field: str = _DEFAULT_COMPANY_NAME_FIELD,
    snapshot_date_field: str = _DEFAULT_SNAPSHOT_DATE_FIELD,
) -> PeerUniverseSnapshot:
    """`classification_rows`(通常はEquities Master Payloadの生Row群)から、
    `target_entity_code`と同一Classification Codeを持つPeer Candidateの
    集合をfail closedで解決する。

    **架空のUniverseを組み立てない**: `classification_rows`が空、
    `target_entity_code`が見つからない、Classification Code自体が不明
    (None/空)のいずれの場合も`UniverseResolution.DATA_UNAVAILABLE`を
    返し(0件のCandidateを「Peerが存在しない」と偽って返さない)、
    `pit_note`に理由を明示する。

    **Entity Identity Ambiguity(要件v1 §8)**: 複数のProvider Codeが
    同一Internal Codeへ正規化される、または同一Internal Codeで
    Classification Code/会社名が食い違う場合は、そのInternal Codeを
    Candidate集合から除外し(架空の一意性を主張しない)、`pit_note`へ
    件数を明記する。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    if not classification_rows:
        return PeerUniverseSnapshot(
            target_entity_code=target_entity_code,
            as_of=as_of,
            classification_system=classification_system,
            target_classification_code=None,
            candidates=(),
            resolution=UniverseResolution.DATA_UNAVAILABLE,
            classification_snapshot_as_of=None,
            pit_note="classification_rowsが空です(Classification Dataそのものが取得されていません)",
        )

    snapshot_dates: set[date] = set()
    entity_rows: dict[str, list[dict[str, str | None]]] = {}
    # Stage 3.17.1(D0096 Finding 2): Dateが欠損した行を`snapshot_dates`から
    # 静かに除外するだけでは、「Dateが無い行が存在する」という事実自体が
    # 失われる(Codex reproduction: Target行のみDate=as_ofでPeer候補行の
    # Date=Noneの場合、Peer候補行を無視してTarget行だけからRESOLVEDと
    # 誤判定できてしまう)。正規化に成功した行ごとにDate有無を記録する。
    missing_date_entity_codes: set[str] = set()
    for row in classification_rows:
        raw_date = row.get(snapshot_date_field)
        has_date = raw_date is not None and raw_date != ""
        if has_date:
            snapshot_dates.add(date.fromisoformat(str(raw_date)))
        provider_code = row.get(code_field)
        if provider_code is None:
            continue
        try:
            internal_code = normalize_provider_code_to_internal(str(provider_code))
        except TickerCodeNormalizationError:
            continue
        if not has_date:
            missing_date_entity_codes.add(internal_code)
        entity_rows.setdefault(internal_code, []).append(
            {
                "provider_code": str(provider_code),
                "classification_code": _extract_str(row, classification_field),
                "company_name": _extract_str(row, company_name_field),
            }
        )

    if len(snapshot_dates) > 1:
        raise ValueError(
            f"classification_rowsに複数の{snapshot_date_field!r}が混在しています"
            f"(単一Snapshotではありません、fail closed): {sorted(d.isoformat() for d in snapshot_dates)}"
        )
    classification_snapshot_as_of = next(iter(snapshot_dates), None)

    ambiguous_entity_codes: list[str] = []
    resolved_rows: dict[str, dict[str, str | None]] = {}
    for internal_code, rows in entity_rows.items():
        distinct = {(r["classification_code"], r["company_name"], r["provider_code"]) for r in rows}
        if len(distinct) > 1:
            ambiguous_entity_codes.append(internal_code)
            continue
        resolved_rows[internal_code] = rows[0]

    if target_entity_code not in resolved_rows:
        return PeerUniverseSnapshot(
            target_entity_code=target_entity_code,
            as_of=as_of,
            classification_system=classification_system,
            target_classification_code=None,
            candidates=(),
            resolution=UniverseResolution.DATA_UNAVAILABLE,
            classification_snapshot_as_of=classification_snapshot_as_of,
            pit_note="target_entity_codeがclassification_rowsから一意に解決できません(ENTITY_IDENTITY_AMBIGUOUSまたは不在)",
        )

    target_classification_code = resolved_rows[target_entity_code]["classification_code"]
    if target_classification_code is None:
        return PeerUniverseSnapshot(
            target_entity_code=target_entity_code,
            as_of=as_of,
            classification_system=classification_system,
            target_classification_code=None,
            candidates=(),
            resolution=UniverseResolution.DATA_UNAVAILABLE,
            classification_snapshot_as_of=classification_snapshot_as_of,
            pit_note="target_entityのclassification_codeがclassification_rows上でNone/空です",
        )

    candidates = tuple(
        sorted(
            (
                PeerCandidate(
                    entity_code=code,
                    provider_code=row["provider_code"],
                    company_name=row["company_name"],
                    classification_system=classification_system,
                    classification_code=row["classification_code"],
                )
                for code, row in resolved_rows.items()
                if code != target_entity_code and row["classification_code"] == target_classification_code
            ),
            key=lambda c: c.entity_code,
        )
    )

    if classification_snapshot_as_of is None:
        resolution = UniverseResolution.PARTIAL
        pit_note = f"classification_rowsに{snapshot_date_field!r}が無く、Classification取得時点を確認できません(PIT未確認)"
    elif classification_snapshot_as_of == as_of.date():
        resolution = UniverseResolution.RESOLVED
        pit_note = "classification_snapshot_as_ofがas_ofと一致しており、Classification MembershipはPIT-safeです"
    else:
        resolution = UniverseResolution.PARTIAL
        direction = "後" if classification_snapshot_as_of > as_of.date() else "前"
        pit_note = (
            f"classification_snapshot_as_of({classification_snapshot_as_of.isoformat()})がas_of"
            f"({as_of.date().isoformat()})より{direction}です。この間にClassificationが変更されていない"
            "という保証は無く(今日の分類を過去へ無条件に遡らせない、要件v1 §6)、Membership自体はPIT未証明です"
            "(fail closed、resolution=PARTIAL)。"
        )

    incomplete_entity_codes = tuple(sorted(missing_date_entity_codes))
    ambiguous_entity_codes_tuple = tuple(sorted(ambiguous_entity_codes))

    # Stage 3.17.1(D0096 Finding 2): Date欠損行・Entity Identity Ambiguous行が
    # 1件でも存在すれば、Snapshot Completenessを証明できないため、たとえ
    # Date一致でも`RESOLVED`を主張しない(fail closed、`PeerUniverseSnapshot.
    # __post_init__`が同じ制約を型としても強制する、Defense-in-depth)。
    if (incomplete_entity_codes or ambiguous_entity_codes_tuple) and resolution == UniverseResolution.RESOLVED:
        resolution = UniverseResolution.PARTIAL
        pit_note = (
            "classification_snapshot_as_ofはas_ofと一致していますが、Snapshot Completenessを"
            "保証できないEntityが存在するためRESOLVEDにしません(fail closed、要件v1 §4 Finding 2): "
            f"incomplete_entity_codes={list(incomplete_entity_codes)}、"
            f"ambiguous_entity_codes={list(ambiguous_entity_codes_tuple)}"
        )
    elif ambiguous_entity_codes_tuple:
        pit_note += f" 注: {len(ambiguous_entity_codes_tuple)}件のInternal CodeがEntity Identity Ambiguousのため除外しました。"

    return PeerUniverseSnapshot(
        target_entity_code=target_entity_code,
        as_of=as_of,
        classification_system=classification_system,
        target_classification_code=target_classification_code,
        candidates=candidates,
        resolution=resolution,
        classification_snapshot_as_of=classification_snapshot_as_of,
        pit_note=pit_note,
        incomplete_entity_codes=incomplete_entity_codes,
        ambiguous_entity_codes=ambiguous_entity_codes_tuple,
    )


__all__ = ["resolve_peer_candidate_universe"]
