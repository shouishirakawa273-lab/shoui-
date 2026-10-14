"""`lib.peer.universe.resolve_peer_candidate_universe()`(Stage 3.17、
D0095)。

PIT Classification Guard(要件v1 §6/§9)が最重要: Classification
Snapshotの基準日がResearch as_ofと一致しない限り、`UniverseResolution.
RESOLVED`にしてはならない(今日の分類を過去へBackfillしない)。実際の
Local Snapshot(`equities_master.json`)で確認済みのField名(`Code`/
`S33`/`CoNameEn`/`Date`)をそのままFixtureへ使う。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from lib.peer.universe import resolve_peer_candidate_universe
from lib.universe import UniverseResolution

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_TARGET = "7203"


def _row(code: str, *, s33: str, name: str, snapshot_date: str) -> dict[str, object]:
    return {"Code": f"{code}0", "S33": s33, "CoNameEn": name, "Date": snapshot_date}


def _base_rows(snapshot_date: str) -> list[dict[str, object]]:
    return [
        _row("7203", s33="3700", name="TOYOTA MOTOR CORPORATION", snapshot_date=snapshot_date),
        _row("7267", s33="3700", name="HONDA MOTOR CO.,LTD.", snapshot_date=snapshot_date),
        _row("7201", s33="3700", name="NISSAN MOTOR CO.,LTD.", snapshot_date=snapshot_date),
        _row("6758", s33="3650", name="SONY GROUP CORPORATION", snapshot_date=snapshot_date),  # different sector
        _row("3626", s33="5250", name="TIS INC.", snapshot_date=snapshot_date),  # different sector
    ]


def test_snapshot_date_matches_as_of_resolves_pit_safe() -> None:
    rows = _base_rows("2024-11-15")
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.RESOLVED
    assert snapshot.target_classification_code == "3700"
    assert [c.entity_code for c in snapshot.candidates] == ["7201", "7267"]
    assert _TARGET not in [c.entity_code for c in snapshot.candidates]


def test_snapshot_date_after_as_of_does_not_resolve() -> None:
    rows = _base_rows("2026-08-17")  # postdates as_of, matches real D0094 observation
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.PARTIAL
    assert "PIT" in snapshot.pit_note or "後" in snapshot.pit_note
    # Candidates are still surfaced (for architecture/testing) but not PIT-confirmed.
    assert [c.entity_code for c in snapshot.candidates] == ["7201", "7267"]


def test_snapshot_date_before_as_of_does_not_resolve() -> None:
    rows = _base_rows("2020-01-01")
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.PARTIAL


def test_empty_rows_data_unavailable() -> None:
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=[])
    assert snapshot.resolution == UniverseResolution.DATA_UNAVAILABLE
    assert snapshot.candidates == ()


def test_target_not_found_data_unavailable() -> None:
    rows = [_row("7267", s33="3700", name="HONDA", snapshot_date="2024-11-15")]
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.DATA_UNAVAILABLE


def test_target_classification_missing_data_unavailable() -> None:
    rows = [
        _row("7203", s33="", name="TOYOTA", snapshot_date="2024-11-15"),
        _row("7267", s33="3700", name="HONDA", snapshot_date="2024-11-15"),
    ]
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.DATA_UNAVAILABLE


def test_entity_identity_ambiguous_row_excluded_not_crashed() -> None:
    rows = [
        _row("7203", s33="3700", name="TOYOTA", snapshot_date="2024-11-15"),
        # Same provider code "72670" appears twice with conflicting sector -> ambiguous, must be dropped safely.
        {"Code": "72670", "S33": "3700", "CoNameEn": "HONDA", "Date": "2024-11-15"},
        {"Code": "72670", "S33": "9999", "CoNameEn": "HONDA-DUP", "Date": "2024-11-15"},
    ]
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert "7267" not in [c.entity_code for c in snapshot.candidates]
    assert snapshot.ambiguous_entity_codes == ("7267",)
    # D0096 Finding 2: Ambiguous行が存在する場合、Date一致でもRESOLVEDにしない。
    assert snapshot.resolution != UniverseResolution.RESOLVED


def test_deterministic_ordering_independent_of_input_order() -> None:
    rows_forward = _base_rows("2024-11-15")
    rows_reversed = list(reversed(rows_forward))
    snap_a = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows_forward)
    snap_b = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows_reversed)
    assert [c.entity_code for c in snap_a.candidates] == [c.entity_code for c in snap_b.candidates]


def test_multiple_snapshot_dates_fail_closed() -> None:
    rows = [
        _row("7203", s33="3700", name="TOYOTA", snapshot_date="2024-11-15"),
        _row("7267", s33="3700", name="HONDA", snapshot_date="2024-11-16"),
    ]
    with pytest.raises(ValueError, match="単一Snapshot"):
        resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)


def test_no_hardcoded_toyota_peers_in_production_logic() -> None:
    """要件v1 §5「恣意的なPeer選定を一切ハードコードしない」の直接検証:
    同じProduction関数を全く異なるTarget/Sectorへ適用しても、正しく動作
    することを確認する(Toyota固有のLogicが混入していないことの証明)。"""
    rows = [
        _row("1001", s33="AAAA", name="X-CORP", snapshot_date="2024-11-15"),
        _row("1002", s33="AAAA", name="Y-CORP", snapshot_date="2024-11-15"),
        _row("1003", s33="BBBB", name="Z-CORP", snapshot_date="2024-11-15"),
    ]
    snapshot = resolve_peer_candidate_universe(target_entity_code="1001", as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.RESOLVED
    assert [c.entity_code for c in snapshot.candidates] == ["1002"]


# --- D0096 Finding 2: Classification Snapshot Completeness (regression E) -----


def test_regression_e_mixed_date_resolution_not_resolved() -> None:
    """要件v1 §16-E / Codex Adversarial Reproduction `mixed_date_
    resolution`: Target行のみDate=as_ofで、Peer候補行(7267)がDate=None
    の場合、Peer候補行の存在によりSnapshot Completenessが証明できず、
    resolution=RESOLVEDにならない(以前は`mixed_date_resolution RESOLVED
    ['7267']`という誤判定が再現した)。"""
    rows = [
        {"Code": "72030", "S33": "3700", "CoNameEn": "TOYOTA", "Date": "2024-11-15"},
        {"Code": "72670", "S33": "3700", "CoNameEn": "HONDA", "Date": None},  # missing Date
    ]
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution != UniverseResolution.RESOLVED
    assert "7267" in snapshot.incomplete_entity_codes
    assert [c.entity_code for c in snapshot.candidates] == ["7267"]  # still surfaced as a Candidate, just not RESOLVED


def test_regression_e_all_rows_with_matching_date_still_resolves() -> None:
    """Regression Eの対照Test: 全行にDateがあり一致していればRESOLVEDの
    まま(Over-Correctionしていないことの確認)。"""
    rows = _base_rows("2024-11-15")
    snapshot = resolve_peer_candidate_universe(target_entity_code=_TARGET, as_of=_AS_OF, classification_rows=rows)
    assert snapshot.resolution == UniverseResolution.RESOLVED
    assert snapshot.incomplete_entity_codes == ()
    assert snapshot.ambiguous_entity_codes == ()
