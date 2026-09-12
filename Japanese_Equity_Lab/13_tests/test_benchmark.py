from __future__ import annotations

import pytest
from lib.backtest.benchmark import BenchmarkReturn, ReturnType, compare_to_benchmark


def test_compare_to_benchmark_computes_excess_return() -> None:
    topix = BenchmarkReturn(benchmark_name="TOPIX", return_type=ReturnType.PRICE_RETURN, value=0.03)
    comparison = compare_to_benchmark(0.08, topix)
    assert comparison.excess_return == pytest.approx(0.05)
    assert comparison.benchmark_name == "TOPIX"


def test_compare_to_benchmark_rejects_mismatched_return_type() -> None:
    topix_total_return = BenchmarkReturn(benchmark_name="TOPIX (Total Return)", return_type=ReturnType.TOTAL_RETURN, value=0.05)
    with pytest.raises(ValueError, match="Return type"):
        compare_to_benchmark(0.08, topix_total_return, strategy_return_type=ReturnType.PRICE_RETURN)
