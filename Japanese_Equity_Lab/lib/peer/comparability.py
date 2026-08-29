"""Comparability Guard: Peer CandidateがAccepted Comparable Peerかを判定
する(Stage 3.17、D0095、要件v1 §8)。

2段階のGuardを分離する(要件v1 §7/§8):

1. Entity単位(Metricに依存しない): `evaluate_peer_entity_eligibility()`。
   Self-Peer・Sector Mismatch・Classification PIT不確実性。
2. Metric単位: `evaluate_peer_metric_comparability()`。Metric欠損・
   Fiscal Period不整合・Accounting Standard不一致・Stale Data。

**Comparabilityを捏造しない**: いずれのGuardも、判定に必要な情報が
不足している場合はComparableとみなさない(fail closed側へ倒す)。
Guardに落ちたCandidateはSilent Dropせず、理由付きで可視のまま返す。
"""

from __future__ import annotations

from datetime import datetime

from lib.peer.model import (
    STALE_FISCAL_CYCLE_THRESHOLD,
    AcceptedPeer,
    ExcludedPeerCandidate,
    PeerCandidate,
    PeerEntityComparabilityResult,
    PeerExclusionReason,
    PeerMetricAvailability,
    PeerMetricObservation,
    PeerMetricType,
)
from lib.universe import UniverseResolution


def evaluate_peer_entity_eligibility(
    candidate: PeerCandidate,
    *,
    target_entity_code: str,
    target_classification_code: str,
    universe_resolution: UniverseResolution,
    as_of: datetime,
) -> PeerEntityComparabilityResult:
    """Metricに依存しないEntity単位のGuardを評価する(要件v1 §7/§8)。

    `universe_resolution != RESOLVED`(=Classification MembershipがPIT-
    safeと証明できていない、`lib.peer.universe.resolve_peer_candidate_
    universe()`参照)の場合、そのUniverseから生成された全Candidateを
    `CLASSIFICATION_UNAVAILABLE_PIT_SAFE`で排除する(fail closed、
    要件v1 §6「Do not silently assume」)——SECTOR一致自体は満たしていても、
    「as_of時点で本当にその業種だったか」が未証明である限りAcceptedには
    しない。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    reasons: list[PeerExclusionReason] = []
    if candidate.entity_code == target_entity_code:
        reasons.append(PeerExclusionReason.SELF_PEER)
    if candidate.classification_code != target_classification_code:
        reasons.append(PeerExclusionReason.SECTOR_MISMATCH)
    if universe_resolution != UniverseResolution.RESOLVED:
        reasons.append(PeerExclusionReason.CLASSIFICATION_UNAVAILABLE_PIT_SAFE)

    if reasons:
        return PeerEntityComparabilityResult(
            excluded=ExcludedPeerCandidate(
                entity_code=candidate.entity_code,
                reasons=tuple(reasons),
                note=(
                    f"universe_resolution={universe_resolution.value}、"
                    f"candidate.classification_code={candidate.classification_code}、"
                    f"target_classification_code={target_classification_code}"
                ),
            )
        )
    return PeerEntityComparabilityResult(
        accepted=AcceptedPeer(
            entity_code=candidate.entity_code,
            classification_system=candidate.classification_system,
            classification_code=candidate.classification_code,
            as_of=as_of,
        )
    )


def evaluate_peer_metric_comparability(
    metric_type: PeerMetricType,
    *,
    target_observation: PeerMetricObservation,
    peer_observation: PeerMetricObservation,
) -> tuple[PeerExclusionReason, ...]:
    """Metric単位のComparability Guardを評価する(要件v1 §8)。

    `METRIC_UNAVAILABLE`は他のGuardと排他ではない(値が無ければFiscal
    Period/Accounting Standardの比較自体ができないため、値がAVAILABLE
    な場合のみ追加のGuardを評価する)。
    """
    if target_observation.metric_type != metric_type or peer_observation.metric_type != metric_type:
        raise ValueError("target_observation/peer_observationのmetric_typeがmetric_typeと一致しません")

    reasons: list[PeerExclusionReason] = []
    both_available = (
        target_observation.availability == PeerMetricAvailability.AVAILABLE
        and peer_observation.availability == PeerMetricAvailability.AVAILABLE
    )
    if not both_available:
        reasons.append(PeerExclusionReason.METRIC_UNAVAILABLE)
        return tuple(reasons)

    target_fpe = target_observation.fiscal_period_end
    peer_fpe = peer_observation.fiscal_period_end
    if target_fpe is not None and peer_fpe is not None:
        if target_fpe.month != peer_fpe.month:
            reasons.append(PeerExclusionReason.FISCAL_PERIOD_INCOMPARABLE)
        elif target_fpe.year - peer_fpe.year > STALE_FISCAL_CYCLE_THRESHOLD:
            reasons.append(PeerExclusionReason.STALE_FINANCIAL_DATA)

    target_std = target_observation.accounting_standard
    peer_std = peer_observation.accounting_standard
    if target_std is not None and peer_std is not None and target_std != peer_std:
        reasons.append(PeerExclusionReason.ACCOUNTING_STANDARD_MISMATCH)

    return tuple(reasons)


__all__ = ["evaluate_peer_entity_eligibility", "evaluate_peer_metric_comparability"]
