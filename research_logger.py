from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from shadow_v8.config import PATHS, ensure_runtime_dirs


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "value"):
        return value.value
    return str(value)


class ResearchLogger:
    def record(self, snapshot: Any) -> None:
        ensure_runtime_dirs()
        with PATHS["research"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, default=_default) + "\n")

