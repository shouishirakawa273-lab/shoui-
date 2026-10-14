"""`DataCapability.PEER_COMPARISON`追加(Stage 3.17、D0095)のRegression。

単一企業のVALUATIONと、複数企業を横断するCross-Sectional Peer
Comparisonは研究上異なる情報次元であるため、別Capabilityとして追加した
(Entity Identity自体はCapability Enumでは表現しない、`lib.peer.model`の
Typed Fieldが保持する)。
"""

from __future__ import annotations

from lib.evidence.research_artifact import DEFAULT_ALLOWED_CAPABILITIES
from lib.sources.catalog import DataCapability


def test_peer_comparison_capability_exists_and_is_distinct_from_valuation() -> None:
    assert DataCapability.PEER_COMPARISON.value == "PEER_COMPARISON"
    assert DataCapability.PEER_COMPARISON != DataCapability.VALUATION


def test_peer_comparison_not_in_default_allowed_capabilities() -> None:
    """既定ではPeer Comparison Evidenceを許可しない(Stage 3.15既存Guardを
    変更しない、呼び出し側が明示的にallowed_capabilitiesを拡張する必要が
    ある、`13_tests/test_peer_research_artifact_integration.py`参照)。"""
    assert DataCapability.PEER_COMPARISON not in DEFAULT_ALLOWED_CAPABILITIES


def test_all_data_capability_members_still_distinct() -> None:
    values = [c.value for c in DataCapability]
    assert len(values) == len(set(values))
