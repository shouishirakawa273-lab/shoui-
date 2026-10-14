"""Point-quote selection, PIT gates, and non-causal measurements (D0110.2).

Inputs are supplied by the caller. No fetching, forecasting, calendar fallback,
or implicit consensus selection occurs here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.macro_events.model import MacroConsensusSnapshot, MacroEvent, MacroFirstRelease
from lib.macro_events.surprise import MacroSurprise, MacroSurpriseStatus, compute_macro_surprise

from .model import (
    RULE_VERSION,
    EventResponseSchemaError,
    EventWindowSpec,
    LinkResult,
    MarketObservation,
    MeasureKind,
    ObservationSeriesKey,
    ObservedEventWindowResponse,
    ResponseStatus,
    SelectionAudit,
    SurpriseResponseLink,
    WindowKind,
    duration_us,
    require_string,
    require_time,
)

_CONTEXT = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_SURPRISE_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_QUANTUM = Decimal("0.000000000001")


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _validate_series(series: ObservationSeriesKey) -> None:
    # Validate on a fresh instance; never replay a mutating canonicalizer on input.
    ObservationSeriesKey(
        instrument_id=series.instrument_id,
        instrument_definition=series.instrument_definition,
        measure_kind=series.measure_kind,
        unit=series.unit,
        quote_convention=series.quote_convention,
        source_id=series.source_id,
    )


def _schema(record: object, expected_type: type) -> None:
    if not isinstance(record, expected_type):
        raise EventResponseSchemaError(f"expected {expected_type.__name__}")
    # Avoid calling builders / post_init: an invalid stored hash must never be repaired.
    time_fields = {
        MacroEvent: ("scheduled_at", "schedule_available_at", "created_at"),
        MacroFirstRelease: ("actual_public_at", "available_at", "created_at"),
        MacroConsensusSnapshot: ("consensus_snapshot_at", "available_at", "created_at"),
        MacroSurprise: ("calculated_at", "available_at"),
        MarketObservation: ("observed_at", "available_at"),
        ObservedEventWindowResponse: ("actual_public_at", "evaluation_cutoff", "calculated_at", "available_at"),
    }
    for name in time_fields.get(expected_type, ()):
        require_time(getattr(record, name), name)
    if isinstance(record, MarketObservation):
        if not isinstance(record.value, Decimal) or not isinstance(record.series, ObservationSeriesKey):
            raise EventResponseSchemaError("invalid observation structure")
        _validate_series(record.series)


def valid_number(value: Decimal) -> bool:
    return value.is_finite() and len(value.as_tuple().digits) <= 28 and (not value or -12 <= value.adjusted() <= 12)


def economic_key(event_id: str, series: ObservationSeriesKey, window_kind: object) -> str:
    return compute_record_hash({"event_id": event_id, "series": series, "window_kind": window_kind})


def revision_key(
    *,
    economic: str,
    event_hash: str,
    release_id: str,
    release_hash: str,
    window_hash: str,
    pre_hash: str,
    post_hash: str,
) -> str:
    return compute_record_hash(
        {
            "economic_observation_key": economic,
            "event_hash": event_hash,
            "release_id": release_id,
            "release_hash": release_hash,
            "window_hash": window_hash,
            "pre_hash": pre_hash,
            "post_hash": post_hash,
            "measurement_rule_id": RULE_VERSION,
        }
    )


def measure_event_window(
    *,
    response_id: str,
    event: MacroEvent,
    first_release: MacroFirstRelease,
    series: ObservationSeriesKey,
    window: EventWindowSpec,
    observations: Sequence[MarketObservation],
    evaluation_cutoff: datetime,
    calculated_at: datetime,
    supersedes_response_id: str | None = None,
) -> ObservedEventWindowResponse:
    """Latest eligible pre / first eligible post, with explicit exclusion audit.

    Status priority follows v2. A retrospective SUCCESS means the input cutoff
    was respected; output availability still includes the actual calculation time.
    """
    require_string(response_id, "response_id")
    require_time(evaluation_cutoff, "evaluation_cutoff")
    require_time(calculated_at, "calculated_at")
    if supersedes_response_id is not None:
        require_string(supersedes_response_id, "supersedes_response_id")
    _schema(event, MacroEvent)
    _schema(first_release, MacroFirstRelease)
    if not isinstance(series, ObservationSeriesKey) or not isinstance(window, EventWindowSpec):
        raise EventResponseSchemaError("invalid series/window")
    _validate_series(series)
    if not isinstance(window.pre_max_age, timedelta) or not isinstance(window.post_max_lag, timedelta):
        raise EventResponseSchemaError("window distances must be timedelta")
    if not isinstance(window.kind, WindowKind):
        raise EventResponseSchemaError("window kind must be WindowKind")
    if not isinstance(observations, Sequence) or isinstance(observations, str | bytes):
        raise EventResponseSchemaError("observations must be a sequence")
    for observation in observations:
        _schema(observation, MarketObservation)

    t = _utc(first_release.actual_public_at)
    cutoff, calculated = _utc(evaluation_cutoff), _utc(calculated_at)
    offset = window.offset
    invalid_range = False
    pre_start: datetime | None
    post_end: datetime | None
    try:
        target = t + offset if offset is not None else None
        pre_start = t - window.pre_max_age
        post_end = target + window.post_max_lag if target is not None else None
    except OverflowError:
        invalid_range = True
        target = pre_start = post_end = None
    audit = tuple(
        SelectionAudit(
            observation_id=identifier, observation_hash=record_hash, pre_reason="NOT_EVALUATED", post_reason="NOT_EVALUATED"
        )
        for identifier, record_hash in sorted({(o.observation_id, o.record_hash) for o in observations})
    )
    selected_pre: MarketObservation | None = None
    selected_post: MarketObservation | None = None

    def result(
        status: ResponseStatus,
        reason: str | None,
        change: Decimal | None = None,
        change_unit: str | None = None,
        relative: Decimal | None = None,
    ) -> ObservedEventWindowResponse:
        economic = economic_key(event.event_id, series, window.kind)
        revision = None
        if status is ResponseStatus.SUCCESS:
            assert selected_pre is not None and selected_post is not None
            revision = revision_key(
                economic=economic,
                event_hash=event.record_hash,
                release_id=first_release.release_id,
                release_hash=first_release.record_hash,
                window_hash=window.record_hash,
                pre_hash=selected_pre.record_hash,
                post_hash=selected_post.record_hash,
            )
        availability = [calculated, _utc(event.schedule_available_at), _utc(first_release.available_at)]
        availability.extend(_utc(o.available_at) for o in (selected_pre, selected_post) if o is not None)
        return ObservedEventWindowResponse(
            response_id=response_id,
            economic_observation_key=economic,
            measurement_revision_key=revision,
            supersedes_response_id=supersedes_response_id,
            event_id=event.event_id,
            event_version=event.event_version,
            event_hash=event.record_hash,
            release_id=first_release.release_id,
            release_hash=first_release.record_hash,
            actual_public_at=t,
            series=series,
            window_id=window.window_id,
            window_kind=window.kind,
            window_policy_hash=window.record_hash,
            target_post_at=target,
            pre=selected_pre,
            post=selected_post,
            pre_age_us=duration_us(t - _utc(selected_pre.observed_at)) if selected_pre is not None else None,
            post_lag_us=duration_us(_utc(selected_post.observed_at) - target)
            if selected_post is not None and target is not None
            else None,
            selection_audit=audit,
            measurement_rule_id=RULE_VERSION,
            change_value=change,
            change_unit=change_unit,
            relative_change_percent=relative,
            relative_change_unit="PERCENT" if relative is not None else None,
            evaluation_cutoff=cutoff,
            calculated_at=calculated,
            available_at=max(availability),
            status=status,
            reason=reason,
        )

    if not all(verify_record_integrity(r) for r in (event, first_release, *observations)) or (
        window.record_hash != compute_record_hash(window.hash_payload())
    ):
        return result(ResponseStatus.INTEGRITY_FAILURE, "input hash mismatch")
    by_id: dict[str, MarketObservation] = {}
    for observation in observations:
        previous = by_id.get(observation.observation_id)
        if previous is not None and previous != observation:
            return result(ResponseStatus.INVALID_INPUT, "same observation ID with different content")
        by_id[observation.observation_id] = observation
    if (
        invalid_range
        or window.pre_max_age <= timedelta(0)
        or window.post_max_lag < timedelta(0)
        or calculated < cutoff
        or any(not valid_number(o.value) or _utc(o.available_at) < _utc(o.observed_at) for o in observations)
        or any(o.series.measure_kind is MeasureKind.PRICE and o.value <= 0 for o in observations)
    ):
        return result(ResponseStatus.INVALID_INPUT, "invalid value, policy, or observation chronology")
    if event.event_id != first_release.event_id or event.event_type != "CPI":
        return result(ResponseStatus.IDENTITY_MISMATCH, "CPI event/release identity required")
    if series.measure_kind is MeasureKind.YIELD and series.unit != "PERCENT":
        return result(ResponseStatus.UNIT_MISMATCH, "yield input requires PERCENT")
    if offset is None:
        return result(ResponseStatus.UNSUPPORTED_WINDOW, "Japan next session requires a separate calendar contract")
    if (
        _utc(event.schedule_available_at) > cutoff
        or _utc(first_release.available_at) > cutoff
        or _utc(first_release.available_at) < t
    ):
        return result(ResponseStatus.PIT_INVALID, "event/release unavailable or chronology invalid")
    assert target is not None
    if cutoff < target:
        return result(ResponseStatus.WINDOW_NOT_COMPLETE, "post target is after cutoff")

    pre_candidates, post_candidates = [], []
    pre_in_range, post_in_range = False, False
    audit_items = []
    for observation in sorted(by_id.values(), key=lambda o: o.observation_id):
        observed, available = _utc(observation.observed_at), _utc(observation.available_at)
        if observation.series != series:
            pre_reason = post_reason = "SERIES_MISMATCH"
        else:
            assert pre_start is not None and post_end is not None
            pre_range = pre_start <= observed < t
            post_range = target <= observed <= post_end
            pre_in_range |= pre_range
            post_in_range |= post_range
            pre_reason = (
                "OUTSIDE_WINDOW" if not pre_range else ("AVAILABLE_AFTER_CUTOFF" if available > min(t, cutoff) else "ELIGIBLE")
            )
            post_reason = "OUTSIDE_WINDOW" if not post_range else ("AVAILABLE_AFTER_CUTOFF" if available > cutoff else "ELIGIBLE")
            if pre_reason == "ELIGIBLE":
                pre_candidates.append(observation)
            if post_reason == "ELIGIBLE":
                post_candidates.append(observation)
        audit_items.append(
            SelectionAudit(
                observation_id=observation.observation_id,
                observation_hash=observation.record_hash,
                pre_reason=pre_reason,
                post_reason=post_reason,
            )
        )
    audit = tuple(audit_items)
    if pre_candidates:
        pre_time = max(_utc(o.observed_at) for o in pre_candidates)
        latest = [o for o in pre_candidates if _utc(o.observed_at) == pre_time]
        if len(latest) > 1:
            return result(ResponseStatus.AMBIGUOUS_INPUT, "competing pre observations at selected timestamp")
        selected_pre = latest[0]
    if post_candidates:
        post_time = min(_utc(o.observed_at) for o in post_candidates)
        earliest = [o for o in post_candidates if _utc(o.observed_at) == post_time]
        if len(earliest) > 1:
            return result(ResponseStatus.AMBIGUOUS_INPUT, "competing post observations at selected timestamp")
        selected_post = earliest[0]
    if (not pre_candidates and pre_in_range) or (not post_candidates and post_in_range):
        return result(ResponseStatus.PIT_INVALID, "all in-window candidates unavailable at cutoff")
    if selected_pre is None or selected_post is None:
        return result(ResponseStatus.MISSING_OBSERVATION, "no eligible point observation in requested interval")
    with localcontext(_CONTEXT):
        delta = selected_post.value - selected_pre.value
        relative = None
        if series.measure_kind is MeasureKind.YIELD:
            delta *= Decimal(100)
            unit = "BASIS_POINT"
        else:
            relative = (selected_post.value / selected_pre.value - Decimal(1)) * Decimal(100)
            relative = relative.quantize(_QUANTUM)
            if not relative:
                relative = abs(relative)
            unit = series.unit
        delta = delta.quantize(_QUANTUM)
        if not delta:
            delta = abs(delta)
    return result(ResponseStatus.SUCCESS, None, delta, unit, relative)


def link_surprise_response(
    *,
    link_id: str,
    response: ObservedEventWindowResponse,
    event: MacroEvent,
    anchor_release: MacroFirstRelease,
    surprise: MacroSurprise,
    consensus: MacroConsensusSnapshot,
    first_release: MacroFirstRelease,
    link_cutoff: datetime,
    linked_at: datetime,
) -> LinkResult:
    """Explicit verified references only; no latest-snapshot query or new arithmetic."""
    require_string(link_id, "link_id")
    require_time(link_cutoff, "link_cutoff")
    require_time(linked_at, "linked_at")
    for record, expected in (
        (response, ObservedEventWindowResponse),
        (event, MacroEvent),
        (anchor_release, MacroFirstRelease),
        (surprise, MacroSurprise),
        (consensus, MacroConsensusSnapshot),
        (first_release, MacroFirstRelease),
    ):
        _schema(record, expected)

    def fail(status: ResponseStatus, reason: str) -> LinkResult:
        return LinkResult(status=status, link=None, reason=reason)

    if not all(verify_record_integrity(r) for r in (response, event, anchor_release, surprise, consensus, first_release)):
        return fail(ResponseStatus.INTEGRITY_FAILURE, "reference integrity mismatch")
    if response.status is not ResponseStatus.SUCCESS or _utc(linked_at) < _utc(link_cutoff):
        return fail(ResponseStatus.INVALID_INPUT, "successful response and chronological link time required")
    if (
        any(r.event_id != event.event_id for r in (response, anchor_release, surprise, consensus, first_release))
        or response.event_hash != event.record_hash
        or response.event_version != event.event_version
        or response.release_id != anchor_release.release_id
        or response.release_hash != anchor_release.record_hash
        or response.actual_public_at != anchor_release.actual_public_at
        or surprise.first_release_id != first_release.release_id
        or surprise.consensus_snapshot_id != consensus.consensus_snapshot_id
        or len({surprise.dimension, consensus.dimension, first_release.dimension}) != 1
        or _utc(first_release.actual_public_at) != _utc(response.actual_public_at)
        or surprise.expected_value != consensus.value
        or surprise.actual_value != first_release.actual_first_release
    ):
        return fail(ResponseStatus.IDENTITY_MISMATCH, "event/release/dimension/snapshot references do not match")
    availability = [
        response.available_at,
        event.schedule_available_at,
        anchor_release.available_at,
        surprise.available_at,
        surprise.calculated_at,
        consensus.available_at,
        first_release.available_at,
    ]
    if any(_utc(value) > _utc(link_cutoff) for value in availability):
        return fail(ResponseStatus.PIT_INVALID, "reference unavailable at link cutoff")
    if (
        _utc(first_release.available_at) < _utc(first_release.actual_public_at)
        or _utc(consensus.available_at) < _utc(consensus.consensus_snapshot_at)
        or not valid_number(consensus.value)
        or not valid_number(first_release.actual_first_release)
    ):
        return fail(ResponseStatus.INVALID_INPUT, "invalid reference value or chronology")
    # Frozen D0110.1 uses Python's default Decimal arithmetic and does not record
    # its context. Support that explicit precision-28 contract, independent of
    # this caller's ambient context. Arbitrary legacy contexts cannot be inferred;
    # mismatches fail closed. The response measurement itself remains precision 80.
    with localcontext(_SURPRISE_CONTEXT):
        replay = compute_macro_surprise(
            surprise_id=surprise.surprise_id,
            event=event,
            consensus=consensus,
            first_release=first_release,
            calculation_rule_id=surprise.calculation_rule_id,
            calculated_at=surprise.calculated_at,
            decision_at=link_cutoff,
        )
    if replay.status is not MacroSurpriseStatus.SUCCESS or replay.surprise != surprise:
        return fail(ResponseStatus.INVALID_INPUT, "surprise does not satisfy frozen producer contract")
    link = SurpriseResponseLink(
        link_id=link_id,
        response_id=response.response_id,
        response_hash=response.record_hash,
        event_id=event.event_id,
        event_hash=event.record_hash,
        anchor_release_id=anchor_release.release_id,
        anchor_release_hash=anchor_release.record_hash,
        surprise_id=surprise.surprise_id,
        surprise_hash=surprise.record_hash,
        consensus_snapshot_id=consensus.consensus_snapshot_id,
        consensus_hash=consensus.record_hash,
        first_release_id=first_release.release_id,
        first_release_hash=first_release.record_hash,
        dimension=surprise.dimension,
        link_cutoff=_utc(link_cutoff),
        linked_at=_utc(linked_at),
        available_at=max(_utc(value) for value in (*availability, linked_at)),
    )
    return LinkResult(status=ResponseStatus.SUCCESS, link=link, reason=None)
