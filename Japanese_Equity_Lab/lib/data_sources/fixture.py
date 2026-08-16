"""テスト・ローカルPipeline検証用の DataSourceAdapter 実装(J-Quants API V2形状)。

実際のJ-Quants等への通信を行わず、あらかじめ用意したfixtureデータ(JSON)を
J-Quants V2のペイロードと同じ構造で返す。**合成データであり、実際の株価ではない。**
このセッションは外部APIへ疎通できないため、Backtest Engineの配線
(Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark -> Registry)
をこのAdapterで検証する。JQuantsAdapterと同じ`DataSourceAdapter` Interfaceを満たすため、
Engine側のコードは呼び出し先がfixtureか実APIかを一切区別しない。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from lib.data_sources.base import LIGHT_PLAN_ASSUMED, DataSourceCapabilities, RawFetchResult

RESPONSE_SCHEMA_VERSION = "fixture-v2(synthetic)"


class FixtureDataSourceAdapter:
    """fixture JSONファイルから日次株価・取引カレンダー等を返す(合成データ専用)。

    fixtureファイルの構造は
    ``{"equity_bars": {code: [{"Code":..,"Date":..,"O":..,"H":..,"L":..,"C":..,
    "Vo":..,"AdjFactor":..,"ExRT":..}, ...]}, "trading_calendar": [{"Date":..,
    "HolDiv":..}], "topix_bars": [...], "equities_master": [...]}``
    を想定する(J-Quants V2のフィールド名を模す)。
    """

    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path
        self._data: dict[str, Any] = json.loads(fixture_path.read_text(encoding="utf-8"))

    @property
    def capabilities(self) -> DataSourceCapabilities:
        return LIGHT_PLAN_ASSUMED

    def fetch_equity_bars(self, *, codes: Sequence[str], start_date: date, end_date: date) -> RawFetchResult:
        all_bars: dict[str, list[dict[str, Any]]] = self._data.get("equity_bars", {})
        records: list[dict[str, Any]] = []
        for code in codes:
            for row in all_bars.get(code, []):
                row_date = date.fromisoformat(row["Date"])
                if start_date <= row_date <= end_date:
                    records.append(row)
        return RawFetchResult(
            source="fixture",
            endpoint="fixture:equity_bars",
            request_parameters={"codes": list(codes), "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        all_days: list[dict[str, Any]] = self._data.get("trading_calendar", [])
        records = [row for row in all_days if start_date <= date.fromisoformat(row["Date"]) <= end_date]
        return RawFetchResult(
            source="fixture",
            endpoint="fixture:trading_calendar",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult:
        """fixtureに"topix_bars": [...] が無い場合は空配列を返す(後方互換のため)。"""
        all_topix: list[dict[str, Any]] = self._data.get("topix_bars", [])
        records = [row for row in all_topix if start_date <= date.fromisoformat(row["Date"]) <= end_date]
        return RawFetchResult(
            source="fixture",
            endpoint="fixture:topix_bars",
            request_parameters={"from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_general_index_bars(self, *, index_code: str, start_date: date, end_date: date) -> RawFetchResult:
        """fixtureに"general_index_bars": {index_code: [...]}} が無い場合は空配列を返す。"""
        all_indices: dict[str, list[dict[str, Any]]] = self._data.get("general_index_bars", {})
        records = [row for row in all_indices.get(index_code, []) if start_date <= date.fromisoformat(row["Date"]) <= end_date]
        return RawFetchResult(
            source="fixture",
            endpoint="fixture:general_index_bars",
            request_parameters={"code": index_code, "from": start_date.isoformat(), "to": end_date.isoformat()},
            retrieved_at=datetime.now(UTC),
            data_period=f"{start_date.isoformat()}/{end_date.isoformat()}",
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )

    def fetch_equities_master(self, *, as_of: date | None = None) -> RawFetchResult:
        """fixtureに"equities_master": [...] が無い場合は空配列を返す(後方互換のため)。"""
        records: list[dict[str, Any]] = self._data.get("equities_master", [])
        return RawFetchResult(
            source="fixture",
            endpoint="fixture:equities_master",
            request_parameters={"as_of": as_of.isoformat() if as_of else None},
            retrieved_at=datetime.now(UTC),
            data_period=(as_of.isoformat() if as_of else "current"),
            response_schema_version=RESPONSE_SCHEMA_VERSION,
            payload=records,
        )
