"""JSON管理のウォッチリスト。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

WATCHLIST_DIR = Path(__file__).resolve().parent.parent / "watchlists"


@dataclass
class Watchlist:
    name: str
    codes: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, name: str, directory: Path = WATCHLIST_DIR) -> Watchlist:
        path = directory / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"ウォッチリストが見つかりません: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(name=data.get("name", name), codes=data.get("codes", []))

    def save(self, directory: Path = WATCHLIST_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.name}.json"
        path.write_text(
            json.dumps({"name": self.name, "codes": self.codes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def list_watchlists(directory: Path = WATCHLIST_DIR) -> list[str]:
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))
