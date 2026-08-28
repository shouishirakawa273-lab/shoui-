from __future__ import annotations

from pathlib import Path

import pytest
from lib.errors import AppendOnlyViolationError
from lib.registry.provenance import ProvenanceLink, ProvenanceStore


def test_trace_to_origin_follows_chain_in_order(tmp_path: Path) -> None:
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(ProvenanceLink(link_id="L1", from_type="youtube_url", from_id="YT001", to_type="idea", to_id="I0001"))
    store.add_link(ProvenanceLink(link_id="L2", from_type="idea", from_id="I0001", to_type="hypothesis", to_id="H0001"))
    store.add_link(ProvenanceLink(link_id="L3", from_type="hypothesis", from_id="H0001", to_type="experiment", to_id="BT0001"))

    chain = store.trace_to_origin("experiment", "BT0001")
    assert [link.link_id for link in chain] == ["L1", "L2", "L3"]
    assert chain[0].from_type == "youtube_url"
    assert chain[-1].to_id == "BT0001"


def test_trace_to_origin_with_no_links_returns_empty(tmp_path: Path) -> None:
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    assert store.trace_to_origin("knowledge", "K9999") == []


def test_duplicate_link_id_is_rejected(tmp_path: Path) -> None:
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    link = ProvenanceLink(link_id="L1", from_type="idea", from_id="I0001", to_type="hypothesis", to_id="H0001")
    store.add_link(link)
    with pytest.raises(AppendOnlyViolationError):
        store.add_link(link)


# --- parents_of(Stage 3.15、Multi-Parent Retrieval Hardening) --------------------------


def test_parents_of_returns_all_direct_parents_for_multi_parent_target(tmp_path: Path) -> None:
    """`trace_to_origin()`は同一to_idへの複数Linkを1件へ潰すため、真の多親Target
    (例: Historical Valuation Context、31 direct parents)を正しく取得できない。
    `parents_of()`は`all()`を単純Filterするのみで、その全件を返す。"""
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(ProvenanceLink(link_id="L1", from_type="per", from_id="PER_A", to_type="context", to_id="CTX0001"))
    store.add_link(ProvenanceLink(link_id="L2", from_type="per", from_id="PER_B", to_type="context", to_id="CTX0001"))
    store.add_link(ProvenanceLink(link_id="L3", from_type="per", from_id="PER_C", to_type="context", to_id="CTX0001"))

    parents = store.parents_of("context", "CTX0001")
    assert {link.from_id for link in parents} == {"PER_A", "PER_B", "PER_C"}
    assert len(parents) == 3

    # 既存trace_to_origin()の挙動は変更しない(複数親のうち最後の1件のみを辿る)。
    traced = store.trace_to_origin("context", "CTX0001")
    assert len(traced) == 1


def test_parents_of_with_no_matching_links_returns_empty(tmp_path: Path) -> None:
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(ProvenanceLink(link_id="L1", from_type="per", from_id="PER_A", to_type="context", to_id="CTX0001"))
    assert store.parents_of("context", "CTX9999") == []
    assert store.parents_of("other_type", "CTX0001") == []
