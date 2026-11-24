"""銘柄種別判定のテスト。実APIには接続しない。

`ProdCat` の値は2026-11-24の実観測(72030→`011`、89510→`013`)と公式コード表に
基づく。この判定は**値を見てからソースを選ばない**ための土台で、誤ると
「取得不可なものを自作値で埋める」側へ倒れる。
"""

from __future__ import annotations

import logging

import pytest
from lib.screener.instrument import InstrumentKind, classify_codes, classify_prod_cat


@pytest.mark.parametrize(
    ("prod_cat", "expected"),
    [
        ("011", InstrumentKind.SHARE),
        ("021", InstrumentKind.SHARE),
        ("024", InstrumentKind.SHARE),
        ("013", InstrumentKind.REIT),
        ("022", InstrumentKind.REIT),
        ("012", InstrumentKind.OTHER),
        ("014", InstrumentKind.OTHER),
        ("023", InstrumentKind.OTHER),
    ],
)
def test_official_codes_classify(prod_cat: str, expected: InstrumentKind) -> None:
    assert classify_prod_cat(prod_cat) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_absent_prod_cat_is_unknown(raw: str | None) -> None:
    """公式には欠損が無いはずなので、起きたら調査対象。OTHERへ落とさない。"""
    assert classify_prod_cat(raw) is InstrumentKind.UNKNOWN


def test_unseen_prod_cat_is_unknown_not_other(caplog: pytest.LogCaptureFixture) -> None:
    """新しい商品区分をOTHER(既知だが対象外)に混ぜない。未知は未知で露出させる。"""
    with caplog.at_level(logging.WARNING, logger="lib.screener.instrument"):
        assert classify_prod_cat("099") is InstrumentKind.UNKNOWN
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_whitespace_is_tolerated() -> None:
    assert classify_prod_cat(" 013 ") is InstrumentKind.REIT


# --- master payload からの引き当て ---

_MASTER = [
    {"Code": "72030", "ProdCat": "011", "CoName": "トヨタ自動車"},
    {"Code": "89510", "ProdCat": "013", "CoName": "日本ビルファンド投資法人"},
    {"Code": "13050", "ProdCat": "014", "CoName": "あるETF"},
]


def test_real_observed_codes_classify() -> None:
    """[回帰] 2026-11-24の実観測。これが崩れるとソースのルーティングが壊れる。"""
    kinds = classify_codes(codes=["7203", "8951"], master_payload=_MASTER)
    assert kinds == {"7203": InstrumentKind.SHARE, "8951": InstrumentKind.REIT}


def test_code_absent_from_master_is_unknown(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="lib.screener.instrument"):
        kinds = classify_codes(codes=["9999"], master_payload=_MASTER)
    assert kinds == {"9999": InstrumentKind.UNKNOWN}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_empty_master_makes_everything_unknown() -> None:
    """masterが取れなかった場合。全てUNKNOWNで、黙ってSHAREと仮定しない。"""
    kinds = classify_codes(codes=["7203", "8951"], master_payload=[])
    assert set(kinds.values()) == {InstrumentKind.UNKNOWN}


def test_provider_code_is_not_rewritten_into_internal_code() -> None:
    """5桁と4桁を混同しない。先頭4桁の一致で引くだけにする。"""
    kinds = classify_codes(codes=["7203"], master_payload=_MASTER)
    assert "72030" not in kinds
    assert "7203" in kinds


def test_malformed_master_rows_are_skipped_not_fatal() -> None:
    payload = [{"Code": 7203, "ProdCat": "011"}, {"Code": "89", "ProdCat": "013"}, *_MASTER]
    kinds = classify_codes(codes=["7203"], master_payload=payload)
    assert kinds["7203"] is InstrumentKind.SHARE


def test_missing_prod_cat_field_is_unknown() -> None:
    kinds = classify_codes(codes=["7203"], master_payload=[{"Code": "72030"}])
    assert kinds["7203"] is InstrumentKind.UNKNOWN
