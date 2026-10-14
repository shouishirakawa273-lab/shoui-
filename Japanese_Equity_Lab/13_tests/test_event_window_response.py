"""D0110.2 acceptance and adversarial tests; synthetic points, no external IO."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import verify_record_integrity
from lib.event_responses.measurement import link_surprise_response, measure_event_window
from lib.event_responses.model import (
    EventResponseSchemaError,
    EventWindowSpec,
    MarketObservation,
    MeasureKind,
    ObservationSeriesKey,
    ObservedEventWindowResponse,
    ResponseStatus,
    WindowKind,
)
from lib.event_responses.store import new_link_store, new_response_store, observation_counts, select_measurement_revision
from lib.macro_events.model import build_macro_consensus_snapshot, build_macro_event, build_macro_first_release
from lib.macro_events.surprise import CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1, compute_macro_surprise

T = datetime(2026, 10, 14, 12, 30, tzinfo=UTC)


def macro():
    event = build_macro_event(
        event_id="US_CPI_2026_09",
        event_type="CPI",
        jurisdiction="US",
        scheduled_at=T - timedelta(minutes=1),
        event_period="2026-09",
        source_id="SYNTHETIC_BLS",
        schedule_available_at=T - timedelta(days=10),
        created_at=T - timedelta(days=10),
    )
    release = build_macro_first_release(
        release_id="CPI_RELEASE",
        event_id=event.event_id,
        dimension="HEADLINE_YOY",
        actual_first_release=Decimal("3.3"),
        unit="PERCENT",
        actual_public_at=T,
        available_at=T,
        source_id="SYNTHETIC_BLS",
        created_at=T,
        previous_as_published=Decimal("3.1"),
    )
    consensus = build_macro_consensus_snapshot(
        consensus_snapshot_id="CONS_T5M",
        event_id=event.event_id,
        dimension=release.dimension,
        value=Decimal("3.1"),
        unit="PERCENT",
        consensus_snapshot_at=T - timedelta(minutes=5),
        available_at=T - timedelta(minutes=5),
        provider="SYNTHETIC",
        source_id="SYNTHETIC_CONSENSUS",
        created_at=T - timedelta(minutes=5),
    )
    computed = compute_macro_surprise(
        surprise_id="SURPRISE",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=T,
        decision_at=T,
    )
    assert computed.surprise is not None
    return event, release, consensus, computed.surprise


def series(kind=MeasureKind.PRICE, name="USDJPY"):
    unit = "PERCENT" if kind is MeasureKind.YIELD else "JPY/USD" if name == "USDJPY" else "USD/TROY_OZ"
    definition = (
        (("tenor", "10Y"), ("series", "CONSTANT_MATURITY"))
        if kind is MeasureKind.YIELD
        else ((("base", "USD"), ("quote", "JPY")) if name == "USDJPY" else (("contract", "SPOT"), ("quantity", "TROY_OZ")))
    )
    return ObservationSeriesKey(
        instrument_id=name,
        instrument_definition=definition,
        measure_kind=kind,
        unit=unit,
        quote_convention="MID",
        source_id="SYNTHETIC_MARKET",
    )


def window(kind=WindowKind.FIVE_MINUTES, lag=timedelta(seconds=5)):
    return EventWindowSpec(
        window_id="WINDOW_" + kind.value,
        kind=kind,
        policy_version="V1",
        pre_max_age=timedelta(seconds=10),
        post_max_lag=lag,
    )


def quote(identifier, value, at, key=None, available=None):
    return MarketObservation(
        observation_id=identifier,
        series=key or series(),
        value=Decimal(value),
        observed_at=at,
        available_at=available or at,
    )


def measure(points=None, key=None, spec=None, cutoff=None, calculated=None, **kwargs):
    event, release, _, _ = macro()
    key, spec = key or series(), spec or window()
    points = (
        points
        if points is not None
        else (quote("PRE", "150", T - timedelta(seconds=1), key), quote("POST", "151.5", T + timedelta(minutes=5), key))
    )
    return measure_event_window(
        response_id=kwargs.pop("response_id", "RESPONSE"),
        event=kwargs.pop("event", event),
        first_release=kwargs.pop("first_release", release),
        series=key,
        window=spec,
        observations=points,
        evaluation_cutoff=cutoff or T + timedelta(days=2),
        calculated_at=calculated or T + timedelta(days=2),
        **kwargs,
    )


def link(response=None, **kwargs):
    event, release, consensus, surprise = macro()
    return link_surprise_response(
        link_id=kwargs.pop("link_id", "LINK"),
        response=response or measure(),
        event=kwargs.pop("event", event),
        anchor_release=kwargs.pop("anchor_release", release),
        surprise=kwargs.pop("surprise", surprise),
        consensus=kwargs.pop("consensus", consensus),
        first_release=kwargs.pop("first_release", release),
        link_cutoff=kwargs.pop("link_cutoff", T + timedelta(days=3)),
        linked_at=kwargs.pop("linked_at", T + timedelta(days=3)),
    )


@pytest.mark.parametrize(
    "kind,name,pre,post,change,unit,relative",
    [
        (MeasureKind.YIELD, "US10Y", "4", "4.12", "12", "BASIS_POINT", None),
        (MeasureKind.PRICE, "USDJPY", "150", "151.5", "1.5", "JPY/USD", "1"),
        (MeasureKind.PRICE, "GOLD_SPOT", "2000", "1960", "-40", "USD/TROY_OZ", "-2"),
    ],
)
@pytest.mark.parametrize("window_kind", [WindowKind.FIVE_MINUTES, WindowKind.THIRTY_MINUTES, WindowKind.TWENTY_FOUR_HOURS])
def test_acceptance_assets_and_windows(kind, name, pre, post, change, unit, relative, window_kind):
    key, spec = series(kind, name), window(window_kind)
    points = (quote("A", pre, T - timedelta(seconds=1), key), quote("B", post, T + spec.offset, key))
    result = measure(points, key, spec)
    assert result.status is ResponseStatus.SUCCESS
    assert result.change_value == Decimal(change) and result.change_unit == unit
    assert result.relative_change_percent == (Decimal(relative) if relative is not None else None)
    assert result.actual_public_at == T and result.available_at == result.calculated_at
    assert verify_record_integrity(result)


def test_unavailable_latest_pre_falls_back_explicitly_and_records_reason():
    old = quote("OLD", "150", T - timedelta(seconds=2))
    new = quote("NEW", "999", T - timedelta(seconds=1), available=T + timedelta(seconds=1))
    post = quote("POST", "151.5", T + timedelta(minutes=5))
    result = measure((new, post, old))
    assert result.pre == old and result.status is ResponseStatus.SUCCESS
    assert next(a.pre_reason for a in result.selection_audit if a.observation_id == "NEW") == "AVAILABLE_AFTER_CUTOFF"


def test_unavailable_first_post_uses_next_eligible_point_within_explicit_lag():
    cutoff = T + timedelta(minutes=5, seconds=4)
    first = quote("FIRST", "999", T + timedelta(minutes=5), available=cutoff + timedelta(seconds=1))
    second = quote("SECOND", "151.5", T + timedelta(minutes=5, seconds=2))
    result = measure((quote("PRE", "150", T - timedelta(seconds=1)), first, second), cutoff=cutoff)
    assert result.post == second and result.post_lag_us == 2000000


@pytest.mark.parametrize("side", ["pre", "post"])
def test_all_in_window_points_unavailable_returns_pit_invalid(side):
    pre = quote("PRE", "150", T - timedelta(seconds=1), available=T + timedelta(seconds=1) if side == "pre" else None)
    post = quote("POST", "151.5", T + timedelta(minutes=5), available=T + timedelta(days=4) if side == "post" else None)
    result = measure((pre, post))
    assert result.status is ResponseStatus.PIT_INVALID and result.change_value is None


@pytest.mark.parametrize("side", ["pre", "post"])
def test_same_timestamp_different_ids_even_same_value_are_ambiguous(side):
    pre, post = quote("PRE", "150", T - timedelta(seconds=1)), quote("POST", "151.5", T + timedelta(minutes=5))
    competitor = replace(pre if side == "pre" else post, observation_id="OTHER", record_hash="")
    assert measure((pre, post, competitor)).status is ResponseStatus.AMBIGUOUS_INPUT


def test_duplicate_content_is_deduped_and_input_order_does_not_change_hash():
    points = (quote("PRE", "150", T - timedelta(seconds=1)), quote("POST", "151.5", T + timedelta(minutes=5)))
    assert measure((*points, points[0])).record_hash == measure(tuple(reversed(points))).record_hash


def test_same_id_changed_content_is_rejected():
    a = quote("A", "150", T - timedelta(seconds=1))
    b = replace(a, value=Decimal("160"), record_hash="")
    assert measure((a, b)).status is ResponseStatus.INVALID_INPUT


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "OTHER_PROVIDER"),
        ("instrument_id", "OTHER_CONTRACT"),
        ("unit", "USD/JPY"),
        ("quote_convention", "LAST"),
        ("instrument_definition", (("base", "JPY"), ("quote", "USD"))),
    ],
)
def test_other_series_is_never_selected(field, value):
    wrong = replace(series(), **{field: value})
    result = measure((quote("WRONG", "150", T - timedelta(seconds=1), wrong), quote("POST", "151.5", T + timedelta(minutes=5))))
    assert result.status is ResponseStatus.MISSING_OBSERVATION
    assert result.selection_audit[1].pre_reason == "SERIES_MISMATCH"


@pytest.mark.parametrize(
    "pre_time,post_time",
    [
        (T, T + timedelta(minutes=5)),
        (T - timedelta(seconds=11), T + timedelta(minutes=5)),
        (T - timedelta(seconds=1), T + timedelta(minutes=5, seconds=6)),
    ],
)
def test_outside_window_or_same_time_pre_is_missing(pre_time, post_time):
    assert (
        measure((quote("PRE", "150", pre_time), quote("POST", "151.5", post_time))).status is ResponseStatus.MISSING_OBSERVATION
    )


def test_window_incomplete_and_japan_session_unsupported():
    assert measure(cutoff=T + timedelta(minutes=4)).status is ResponseStatus.WINDOW_NOT_COMPLETE
    assert measure(spec=window(WindowKind.JAPAN_NEXT_SESSION)).status is ResponseStatus.UNSUPPORTED_WINDOW


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "0", "-1", "1E13", "1E-13"])
def test_invalid_price_values_fail_closed(value):
    result = measure((quote("BAD", value, T - timedelta(seconds=1)),))
    assert result.status is ResponseStatus.INVALID_INPUT
    assert result.change_value is result.relative_change_percent is None


@pytest.mark.parametrize("pre,post", [("0", "0"), ("-0.1", "0"), ("-0.1", "-0.2")])
def test_zero_negative_yield_valid_and_never_price_return(pre, post):
    key = series(MeasureKind.YIELD, "US10Y")
    result = measure((quote("PRE", pre, T - timedelta(seconds=1), key), quote("POST", post, T + timedelta(minutes=5), key)), key)
    assert result.status is ResponseStatus.SUCCESS
    assert result.change_value == (Decimal(post) - Decimal(pre)) * 100
    assert result.relative_change_percent is None


def test_wrong_yield_unit_and_invalid_chronology():
    key = replace(series(MeasureKind.YIELD, "US10Y"), unit="BASIS_POINT")
    assert measure((), key).status is ResponseStatus.UNIT_MISMATCH
    bad = quote("BAD", "150", T - timedelta(seconds=1), available=T - timedelta(seconds=2))
    assert measure((bad,)).status is ResponseStatus.INVALID_INPUT


def test_naive_time_or_bad_element_raises_schema_error():
    with pytest.raises(EventResponseSchemaError):
        quote("BAD", "1", T.replace(tzinfo=None))
    with pytest.raises(EventResponseSchemaError):
        measure((object(),))
    with pytest.raises(EventResponseSchemaError):
        measure(cutoff=T.replace(tzinfo=None))


def test_tampering_and_invalid_window_priority():
    point = quote("PRE", "150", T - timedelta(seconds=1))
    object.__setattr__(point, "value", Decimal("999"))
    assert measure((point,)).status is ResponseStatus.INTEGRITY_FAILURE
    assert measure(spec=replace(window(), pre_max_age=timedelta(0), record_hash="")).status is ResponseStatus.INVALID_INPUT


def test_calculation_is_later_than_cutoff_and_macro_future_inputs_rejected():
    assert measure(calculated=T).status is ResponseStatus.INVALID_INPUT
    event, release, _, _ = macro()
    assert (
        measure(event=replace(event, schedule_available_at=T + timedelta(days=4), record_hash="bad")).status
        is ResponseStatus.INTEGRITY_FAILURE
    )
    future = replace(release, available_at=T + timedelta(days=4))
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    future = replace(future, record_hash=compute_record_hash(asdict(future)))
    assert measure(first_release=future).status is ResponseStatus.PIT_INVALID


def test_decimal_context_independent_nonterminating_division_and_negative_zero():
    points = (quote("PRE", "3", T - timedelta(seconds=1)), quote("POST", "4", T + timedelta(minutes=5)))
    reference = measure(points)
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = "ROUND_DOWN"
        other = measure(points)
    assert reference == other and reference.relative_change_percent == Decimal("33.333333333333")
    equal = measure((quote("PRE", "3", T - timedelta(seconds=1)), quote("POST", "3", T + timedelta(minutes=5))))
    assert equal.status is ResponseStatus.SUCCESS and equal.change_value == 0
    assert not equal.change_value.is_signed()


def test_utc_elapsed_24h_across_dst_not_wall_clock_day():
    ny = ZoneInfo("America/New_York")
    event, release, _, _ = macro()
    local_t = datetime(2026, 11, 1, 0, 30, tzinfo=ny)
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    release = replace(release, actual_public_at=local_t, available_at=local_t, created_at=local_t)
    release = replace(release, record_hash=compute_record_hash(asdict(release)))
    utc_t = local_t.astimezone(UTC)
    post = utc_t + timedelta(hours=24)
    result = measure(
        (quote("PRE", "150", utc_t - timedelta(seconds=1)), quote("POST", "151.5", post)),
        spec=window(WindowKind.TWENTY_FOUR_HOURS),
        event=event,
        first_release=release,
        cutoff=post,
        calculated=post,
    )
    assert result.status is ResponseStatus.SUCCESS and result.target_post_at == post


def test_link_success_two_snapshots_do_not_duplicate_response(tmp_path):
    response = measure()
    first = link(response)
    assert first.status is ResponseStatus.SUCCESS
    event, release, consensus, _ = macro()
    earlier = replace(consensus, consensus_snapshot_id="CONS_T3D", value=Decimal("3.0"), record_hash="")
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    earlier = replace(earlier, record_hash=compute_record_hash(asdict(earlier)))
    computed = compute_macro_surprise(
        surprise_id="EARLIER_SURPRISE",
        event=event,
        consensus=earlier,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=T,
    )
    second = link(response, link_id="OTHER_LINK", consensus=earlier, surprise=computed.surprise)
    assert second.status is ResponseStatus.SUCCESS
    responses = new_response_store(tmp_path / "response.jsonl")
    links = new_link_store(tmp_path / "link.jsonl", responses)
    responses.record(response)
    links.record(first.link)
    links.record(second.link)
    assert len(links.all()) == 2 and observation_counts(responses.all()) == (1, 1, 1)


@pytest.mark.parametrize("which", ["event", "release", "dimension", "snapshot"])
def test_valid_hash_wrong_reference_is_rejected(which):
    event, release, consensus, surprise = macro()
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    if which == "event":
        surprise = replace(surprise, event_id="OTHER_CPI")
    elif which == "release":
        surprise = replace(surprise, first_release_id="OTHER_RELEASE")
    elif which == "dimension":
        surprise = replace(surprise, dimension="CORE_YOY")
    else:
        surprise = replace(surprise, consensus_snapshot_id="OTHER_SNAPSHOT")
    surprise = replace(surprise, record_hash=compute_record_hash(asdict(surprise)))
    assert link(surprise=surprise).status is ResponseStatus.IDENTITY_MISMATCH


def test_future_surprise_calculation_and_forged_arithmetic_rejected():
    _, _, _, surprise = macro()
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    future = replace(surprise, calculated_at=T + timedelta(days=4))
    future = replace(future, record_hash=compute_record_hash(asdict(future)))
    assert link(surprise=future).status is ResponseStatus.PIT_INVALID
    wrong = replace(surprise, surprise_value=Decimal("999"))
    wrong = replace(wrong, record_hash=compute_record_hash(asdict(wrong)))
    assert link(surprise=wrong).status is ResponseStatus.INVALID_INPUT


def test_link_reference_tamper_and_failed_response_rejected():
    _, _, consensus, _ = macro()
    object.__setattr__(consensus, "value", Decimal("999"))
    assert link(consensus=consensus).status is ResponseStatus.INTEGRITY_FAILURE
    assert link(response=measure(())).status is ResponseStatus.INVALID_INPUT


def test_correction_recalculation_policy_identity_and_store(tmp_path):
    store = new_response_store(tmp_path / "response.jsonl")
    original = measure()
    store.record(original)
    assert store.record(original) == original and len(store.all()) == 1
    recalculated = measure(response_id="RECALCULATED", calculated=T + timedelta(days=3))
    corrected = measure(
        (quote("PRE", "150", T - timedelta(seconds=1)), quote("NEW_POST", "152", T + timedelta(minutes=5))),
        response_id="CORRECTED",
        supersedes_response_id=original.response_id,
    )
    policy = measure(spec=replace(window(), policy_version="V2", record_hash=""), response_id="POLICY")
    for record in (recalculated, corrected, policy):
        store.record(record)
    assert recalculated.measurement_revision_key == original.measurement_revision_key
    assert corrected.measurement_revision_key != original.measurement_revision_key != policy.measurement_revision_key
    assert observation_counts(store.all()) == (4, 1, 1)
    assert store.get(original.response_id) == original
    assert (
        select_measurement_revision(
            store.all(), economic_observation_key=original.economic_observation_key, response_id="CORRECTED"
        )
        == corrected
    )
    with pytest.raises(AppendOnlyViolationError):
        store.record(measure(response_id=original.response_id, calculated=T + timedelta(days=3)))


@pytest.mark.parametrize("parent", ["MISSING", "SELF", "OTHER_EVENT"])
def test_invalid_correction_parent_rejected(tmp_path, parent):
    store = new_response_store(tmp_path / "response.jsonl")
    if parent == "OTHER_EVENT":
        store.record(measure(spec=window(WindowKind.THIRTY_MINUTES), response_id=parent))
    result = measure(response_id="SELF", supersedes_response_id=parent)
    with pytest.raises(AppendOnlyViolationError):
        store.record(result)


def test_store_tamper_and_missing_response_link_rejected(tmp_path):
    path = tmp_path / "response.jsonl"
    store = new_response_store(path)
    store.record(measure())
    path.write_text(path.read_text(encoding="utf-8").replace("151.5", "999"), encoding="utf-8")
    with pytest.raises(EventResponseSchemaError):
        store.all()
    links = new_link_store(tmp_path / "links.jsonl", new_response_store(tmp_path / "empty.jsonl"))
    with pytest.raises(AppendOnlyViolationError):
        links.record(link().link)


def test_immutable_and_noncausal():
    result = measure()
    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"
    assert result.non_causal_label == "OBSERVED_ASSOCIATION_ONLY"
    fields = ObservedEventWindowResponse.__dataclass_fields__
    assert not {"expected_return", "company_id", "scenario_probability", "decision"} & fields.keys()


def test_tampered_nested_definition_is_never_repaired_or_mutated():
    pre = quote("PRE", "150", T - timedelta(seconds=1))
    changed = tuple(reversed(pre.series.instrument_definition))
    object.__setattr__(pre.series, "instrument_definition", changed)
    assert not verify_record_integrity(pre)
    result = measure((pre,))
    assert result.status is ResponseStatus.INTEGRITY_FAILURE
    assert pre.series.instrument_definition == changed
    assert not verify_record_integrity(pre)


@pytest.mark.parametrize("tamper", ["reorder", "empty_hash"])
def test_store_verifies_raw_payload_before_normalization(tmp_path, tamper):
    import json

    path = tmp_path / "responses.jsonl"
    store = new_response_store(path)
    store.record(measure())
    data = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "reorder":
        data["pre"]["series"]["instrument_definition"].reverse()
    else:
        data["record_hash"] = ""
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EventResponseSchemaError):
        store.all()


@pytest.mark.parametrize("failure", ["incomplete", "invalid", "integrity"])
def test_failure_records_bind_input_set_and_remain_order_independent(failure):
    a, b = quote("A", "150", T - timedelta(seconds=1)), quote("B", "151", T + timedelta(minutes=5))
    kwargs = {"cutoff": T} if failure == "incomplete" else {}
    if failure == "invalid":
        a = quote("A", "-1", T - timedelta(seconds=1))
    elif failure == "integrity":
        a = replace(a, record_hash="bad")
    first, second = measure((a, b), **kwargs), measure((b, a), **kwargs)
    assert first.status is not ResponseStatus.SUCCESS
    assert first == second and len(first.selection_audit) == 2
    assert measure((a,), **kwargs).record_hash != first.record_hash


def test_extreme_window_distance_returns_typed_failure():
    result = measure(spec=replace(window(), pre_max_age=timedelta.max, record_hash=""))
    assert result.status is ResponseStatus.INVALID_INPUT


def test_frozen_surprise_default_precision_adapter_is_context_independent():
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    event, release, consensus, _ = macro()
    value = Decimal("9.999999999999999999999999999")
    release = replace(release, actual_first_release=value)
    release = replace(release, record_hash=compute_record_hash(asdict(release)))
    consensus = replace(consensus, value=-value)
    consensus = replace(consensus, record_hash=compute_record_hash(asdict(consensus)))
    with localcontext() as ctx:
        ctx.prec = 28
        produced = compute_macro_surprise(
            surprise_id="DEFAULT_CONTEXT",
            event=event,
            consensus=consensus,
            first_release=release,
            calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
            calculated_at=T,
        )
    response = measure(first_release=release)
    with localcontext() as ctx:
        ctx.prec = 2
        linked = link(response, anchor_release=release, first_release=release, consensus=consensus, surprise=produced.surprise)
    assert linked.status is ResponseStatus.SUCCESS


def test_same_event_other_dimension_requires_exact_same_publication_time():
    event, anchor, _, _ = macro()
    other = build_macro_first_release(
        release_id="CORE_RELEASE",
        event_id=event.event_id,
        dimension="CORE_YOY",
        actual_first_release=Decimal("2.5"),
        unit="PERCENT",
        actual_public_at=T,
        available_at=T,
        source_id="SYNTHETIC_BLS",
        created_at=T,
    )
    consensus = build_macro_consensus_snapshot(
        consensus_snapshot_id="CORE_CONSENSUS",
        event_id=event.event_id,
        dimension="CORE_YOY",
        value=Decimal("2.4"),
        unit="PERCENT",
        consensus_snapshot_at=T - timedelta(minutes=5),
        available_at=T - timedelta(minutes=5),
        provider="SYNTHETIC",
        source_id="SYNTHETIC_CONSENSUS",
        created_at=T - timedelta(minutes=5),
    )
    surprise = compute_macro_surprise(
        surprise_id="CORE_SURPRISE",
        event=event,
        consensus=consensus,
        first_release=other,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=T,
    ).surprise
    assert (
        link(anchor_release=anchor, first_release=other, consensus=consensus, surprise=surprise).status is ResponseStatus.SUCCESS
    )
    from dataclasses import asdict

    from lib.evaluation.integrity import compute_record_hash

    delayed = replace(other, actual_public_at=T + timedelta(seconds=1), available_at=T + timedelta(seconds=1))
    delayed = replace(delayed, record_hash=compute_record_hash(asdict(delayed)))
    assert link(first_release=delayed, consensus=consensus, surprise=surprise).status is ResponseStatus.IDENTITY_MISMATCH


def test_elapsed_24h_explicit_lag_no_hidden_session_rollover():
    spec = window(WindowKind.TWENTY_FOUR_HOURS, lag=timedelta(minutes=1))
    points = (
        quote("PRE", "150", T - timedelta(seconds=1)),
        quote("NEXT_SESSION", "151", T + timedelta(hours=24, minutes=1)),
    )
    within = measure(points, spec=spec)
    assert within.status is ResponseStatus.SUCCESS and within.post_lag_us == 60000000
    outside = measure(points, spec=window(WindowKind.TWENTY_FOUR_HOURS, lag=timedelta(seconds=59)))
    assert outside.status is ResponseStatus.MISSING_OBSERVATION


def test_exact_window_boundaries_and_source_versions_are_preserved():
    key = series()
    pre = replace(quote("PRE", "150", T - timedelta(seconds=10), key), source_version="V1", record_hash="")
    post = replace(quote("POST", "151", T + timedelta(minutes=5), key), source_version="V2", record_hash="")
    result = measure((pre, post), spec=window(lag=timedelta(0)))
    assert result.status is ResponseStatus.SUCCESS
    assert result.pre.source_version == "V1" and result.post.source_version == "V2"


def test_ambiguity_precedes_missing_post():
    pre = quote("PRE", "150", T - timedelta(seconds=1))
    same = replace(pre, observation_id="COMPETITOR", record_hash="")
    assert measure((pre, same)).status is ResponseStatus.AMBIGUOUS_INPUT
