"""Benchmark比較(TOPIX等)。

Ver.1はキャピタルゲイン研究が主目的のため、Price Return同士の比較を基本とする。
Total Returnとの混在比較はコードレベルで拒否する。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReturnType(StrEnum):
    PRICE_RETURN = "PRICE_RETURN"
    TOTAL_RETURN = "TOTAL_RETURN"


@dataclass(frozen=True)
class BenchmarkReturn:
    benchmark_name: str
    return_type: ReturnType
    value: float


@dataclass(frozen=True)
class BenchmarkComparison:
    benchmark_name: str
    return_type: ReturnType
    benchmark_return: float
    strategy_return: float
    excess_return: float


def compare_to_benchmark(
    strategy_return: float,
    benchmark: BenchmarkReturn,
    *,
    strategy_return_type: ReturnType = ReturnType.PRICE_RETURN,
) -> BenchmarkComparison:
    """strategy_returnとbenchmarkのreturn_typeが一致しない場合は比較しない。"""
    if strategy_return_type != benchmark.return_type:
        raise ValueError(
            f"Return typeが一致しません(strategy={strategy_return_type}, benchmark={benchmark.return_type})。"
            "Ver.1はPrice Return同士の比較を基本とする(RESEARCH_RULES.md参照)。"
        )
    return BenchmarkComparison(
        benchmark_name=benchmark.benchmark_name,
        return_type=benchmark.return_type,
        benchmark_return=benchmark.value,
        strategy_return=strategy_return,
        excess_return=strategy_return - benchmark.value,
    )
