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
