from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shadow_v8.config import PATHS, ensure_runtime_dirs


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    return str(value)


class StateStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.path = path or PATHS["state"]

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, default=_json_default), encoding="utf-8")


class PositionStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.path = path or PATHS["positions"]

    def load_all(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_all(self, positions: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(positions, indent=2, default=_json_default), encoding="utf-8")


class ClosedTradeStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.path = path or PATHS["closed_trades"]

    def load_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def append(self, trade: dict[str, Any], max_rows: int = 500) -> None:
        rows = self.load_all()
        rows.insert(0, trade)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows[:max_rows], indent=2, default=_json_default), encoding="utf-8")
