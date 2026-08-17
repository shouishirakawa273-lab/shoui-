"""Phase4B-3(D0047): `lib.disclosures.providers.tdnet_cursor.TdnetRetrievalCursorState`のテスト。

このClassはArchitecture骨格のみ(実Adapterへの接続はまだ無い)。Cursorが
DisclosureDocument/PIT Fieldと分離されていること、Timestampとして誤用
できない設計になっていることを確認する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from lib.disclosures.providers.tdnet_cursor import TdnetRetrievalCursorState

_RETRIEVED_AT = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)


def test_cursor_state_requires_tz_aware_retrieved_at() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        TdnetRetrievalCursorState(
            query_date=date(2026, 8, 17),
            cursor_value="abc123",
            previous_cursor=None,
            retrieved_at=datetime(2026, 8, 17, 9, 0),  # tz無し
        )


def test_cursor_state_allows_none_cursor_values_for_initial_retrieval() -> None:
    state = TdnetRetrievalCursorState(
        query_date=date(2026, 8, 17),
        cursor_value="next-cursor-abc",
        previous_cursor=None,
        retrieved_at=_RETRIEVED_AT,
    )
    assert state.previous_cursor is None
    assert state.cursor_value == "next-cursor-abc"


def test_cursor_state_response_snapshot_hash_is_optional() -> None:
    state = TdnetRetrievalCursorState(
        query_date=date(2026, 8, 17),
        cursor_value=None,
        previous_cursor="prev-cursor-xyz",
        retrieved_at=_RETRIEVED_AT,
    )
    assert state.response_snapshot_hash is None


# --- Cursor != Timestamp、DisclosureDocumentとの分離(構造的確認) ---


def test_tdnet_cursor_module_never_imports_disclosure_document_or_availability_basis() -> None:
    """Cursor Stateは`DisclosureDocument`/`AvailabilityBasis`のいずれとも
    一切結びつかないことを、Import構造で確認する(Cursor値からTimestampを
    推測する経路が存在しないことの構造的保証、D0047 §D)。"""
    import lib.disclosures.providers.tdnet_cursor as tdnet_cursor_module

    source = tdnet_cursor_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()
    import_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(("import ", "from "))]
    forbidden_modules = ("lib.disclosures.model", "lib.evidence.model")
    assert not any(module in line for line in import_lines for module in forbidden_modules)


def test_tdnet_retrieval_cursor_state_has_no_market_public_at_or_provider_available_at_field() -> None:
    """CursorがPIT Fieldへ紛れ込む経路が無いことを、Dataclass Fieldの集合で
    直接確認する。"""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(TdnetRetrievalCursorState)}
    assert "market_public_at" not in field_names
    assert "provider_available_at" not in field_names
