from __future__ import annotations

import pytest
from lib.errors import HypothesisImmutabilityError
from lib.schemas.hypothesis import Hypothesis, HypothesisStatus


def _draft(**overrides: object) -> Hypothesis:
    defaults: dict[str, object] = dict(
        hypothesis_id="H0001",
        source_idea_id="I0001",
        claim="決算上方修正後、株価は数週間かけて反応が続く",
        mechanism="アナリスト・機関投資家の情報反映速度の遅れ(underreaction)",
        universe="東証プライム全銘柄",
        signal_definition="会社予想の上方修正発表",
        entry_rule="開示翌営業日始値で買い",
        exit_rule="60営業日後の始値で手仕舞い",
        holding_period="60営業日",
        success_metric="TOPIX比 excess_return > 0 (Test期間)",
        failure_metric="TOPIX比 excess_return <= 0 (Test期間)",
    )
    defaults.update(overrides)
    return Hypothesis(**defaults)  # type: ignore[arg-type]


def test_lock_stores_terms_hash_and_transitions_status() -> None:
    hypothesis = _draft()
    locked = hypothesis.lock()
    assert locked.status == HypothesisStatus.LOCKED
    assert locked.locked_terms_hash == locked.terms_hash()
    # 元のインスタンスはfrozenなので変化しない。
    assert hypothesis.status == HypothesisStatus.DRAFT


def test_cannot_lock_twice() -> None:
    locked = _draft().lock()
    with pytest.raises(HypothesisImmutabilityError):
        locked.lock()


def test_with_status_requires_locked_first() -> None:
    with pytest.raises(HypothesisImmutabilityError):
        _draft().with_status(HypothesisStatus.TESTED)


def test_with_status_advances_lifecycle_without_changing_terms() -> None:
    locked = _draft().lock()
    tested = locked.with_status(HypothesisStatus.TESTED)
    assert tested.status == HypothesisStatus.TESTED
    assert tested.claim == locked.claim
    assert tested.locked_terms_hash == locked.locked_terms_hash


def test_revise_creates_new_id_and_keeps_lineage() -> None:
    locked = _draft().lock()
    revised = locked.revise(new_hypothesis_id="H0002", holding_period="90営業日")
    assert revised.hypothesis_id == "H0002"
    assert revised.parent_hypothesis_id == "H0001"
    assert revised.status == HypothesisStatus.DRAFT
    assert revised.holding_period == "90営業日"
    # 元のLOCKED Hypothesisは書き換わらない。
    assert locked.holding_period != "90営業日"


def test_revise_rejects_non_terms_fields() -> None:
    locked = _draft().lock()
    with pytest.raises(ValueError, match="terms以外"):
        locked.revise(new_hypothesis_id="H0002", hypothesis_id="H9999")


def test_revise_requires_locked_or_later() -> None:
    with pytest.raises(HypothesisImmutabilityError):
        _draft().revise(new_hypothesis_id="H0002")
