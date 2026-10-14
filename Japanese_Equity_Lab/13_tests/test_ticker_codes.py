"""J-Quants Provider Code(5桁)とResearch Lab内部Code(4桁)の正規化テスト。

実SmokeTest確認事実(2026-08-16、DECISIONS.md D0036): request code=7203に対して
Provider側は"Code": "72030"を返す。
"""

from __future__ import annotations

import pytest
from lib.data_sources.ticker_codes import (
    TickerCodeNormalizationError,
    build_provider_to_internal_code_index,
    normalize_provider_code_to_internal,
)


def test_normalizes_confirmed_five_digit_common_stock_pattern() -> None:
    """実SmokeTestで確認された唯一のパターン: "72030" -> "7203"。"""
    assert normalize_provider_code_to_internal("72030") == "7203"


def test_normalizes_other_common_stock_codes() -> None:
    assert normalize_provider_code_to_internal("67580") == "6758"
    assert normalize_provider_code_to_internal("36260") == "3626"


def test_four_digit_code_passes_through_unchanged() -> None:
    """一部Endpointが4桁のまま返す可能性への保守的なフォールバック。"""
    assert normalize_provider_code_to_internal("7203") == "7203"


def test_does_not_blindly_strip_trailing_character() -> None:
    """5桁だが末尾が"0"でない場合(優先株等の可能性)は推測せず例外を送出する。"""
    with pytest.raises(TickerCodeNormalizationError):
        normalize_provider_code_to_internal("72031")


def test_non_digit_code_passes_through_unchanged() -> None:
    """数字以外を含む場合(fixture/testの合成ラベル)は実Provider Codeではありえないため
    そのまま返す(例: "TOPIX_SYNTH"のようなfixture専用の疑似コード)。"""
    assert normalize_provider_code_to_internal("TOPIX_SYNTH") == "TOPIX_SYNTH"
    assert normalize_provider_code_to_internal("PSIM_A") == "PSIM_A"


def test_unexpected_length_raises() -> None:
    with pytest.raises(TickerCodeNormalizationError):
        normalize_provider_code_to_internal("720300")


def test_build_index_maps_provider_codes_to_internal_codes() -> None:
    index = build_provider_to_internal_code_index(["72030", "67580", "36260"])
    assert index == {"7203": "72030", "6758": "67580", "3626": "36260"}


def test_build_index_raises_on_collision() -> None:
    """異なるProvider Codeが同じinternal_codeへ正規化される場合、黙って上書きしない。"""
    with pytest.raises(TickerCodeNormalizationError):
        build_provider_to_internal_code_index(["72030", "7203"])
