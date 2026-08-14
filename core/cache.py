"""SQLiteベースのローカルキャッシュ。

各データソースのレート制限を尊重するため、同一銘柄への再取得を減らす。
取得日時(fetched_at)を必ず保存し、UI側で「このデータはいつ時点のものか」を
表示できるようにする。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from core.models import ForecastSnapshot, Market, StockSnapshot

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cache.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot_cache (
    cache_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    code TEXT NOT NULL,
    market TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


class Cache:
    """銘柄スナップショット / 予想データの取得日時付きキャッシュ。"""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, ttl: timedelta = timedelta(hours=6)):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    @staticmethod
    def _key(kind: str, code: str, market: Market) -> str:
        return f"{kind}:{market.value}:{code.upper()}"

    def get_snapshot(self, code: str, market: Market) -> StockSnapshot | None:
        row = self._get_row("snapshot", code, market)
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["market"] = Market(payload["market"])
        payload["fetched_at"] = datetime.fromisoformat(payload["fetched_at"])
        payload["warnings"] = []  # 警告はキャッシュせず都度再計算する
        return StockSnapshot(**payload)

    def set_snapshot(self, snapshot: StockSnapshot) -> None:
        payload = asdict(snapshot)
        payload["market"] = snapshot.market.value
        payload["fetched_at"] = snapshot.fetched_at.isoformat()
        payload["warnings"] = []
        self._put_row("snapshot", snapshot.code, snapshot.market, payload, snapshot.fetched_at)

    def get_forecast(self, code: str, market: Market) -> ForecastSnapshot | None:
        row = self._get_row("forecast", code, market)
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["market"] = Market(payload["market"])
        payload["fetched_at"] = datetime.fromisoformat(payload["fetched_at"])
        return ForecastSnapshot(**payload)

    def set_forecast(self, forecast: ForecastSnapshot) -> None:
        payload = asdict(forecast)
        payload["market"] = forecast.market.value
        payload["fetched_at"] = forecast.fetched_at.isoformat()
        self._put_row("forecast", forecast.code, forecast.market, payload, forecast.fetched_at)

    def _get_row(self, kind: str, code: str, market: Market) -> sqlite3.Row | None:
        key = self._key(kind, code, market)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM snapshot_cache WHERE cache_key = ?", (key,))
            row = cur.fetchone()
        if row is None:
            return None
        fetched_at = datetime.fromisoformat(row["fetched_at"])
        if datetime.now() - fetched_at > self.ttl:
            return None  # TTL切れ: 再取得させる
        return row

    def _put_row(self, kind: str, code: str, market: Market, payload: dict, fetched_at: datetime) -> None:
        key = self._key(kind, code, market)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshot_cache (cache_key, kind, code, market, payload_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at
                """,
                (key, kind, code, market.value, json.dumps(payload, default=str), fetched_at.isoformat()),
            )
            conn.commit()

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM snapshot_cache")
            conn.commit()
