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
    推測する経路が存在しないことの構造的保証、D0047 §D)。

    ASTベースでImport文を解析する(単純な部分文字列一致だと
    `from lib.disclosures import model`のような分割記法や
    `importlib.import_module()`経由の動的Importを見逃すため、
    pit-auditor Finding対応でAST解析へ強化した)。
    """
    import ast

    import lib.disclosures.providers.tdnet_cursor as tdnet_cursor_module

    source = tdnet_cursor_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        text = f.read()

    forbidden_dotted_names = {"lib.disclosures.model", "lib.evidence.model"}
    imported_dotted_names: set[str] = set()
    tree = ast.parse(text, filename=source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_dotted_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_dotted_names.add(node.module)
            for alias in node.names:
                imported_dotted_names.add(f"{node.module}.{alias.name}")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            imported_dotted_names.add(node.args[0].value)

    assert not (imported_dotted_names & forbidden_dotted_names)
    assert not any(
        imported.startswith(f"{forbidden}.") for imported in imported_dotted_names for forbidden in forbidden_dotted_names
    )


def test_tdnet_retrieval_cursor_state_has_no_market_public_at_or_provider_available_at_field() -> None:
    """CursorがPIT Fieldへ紛れ込む経路が無いことを、Dataclass Fieldの集合で
    直接確認する。"""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(TdnetRetrievalCursorState)}
    assert "market_public_at" not in field_names
    assert "provider_available_at" not in field_names
