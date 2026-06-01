from __future__ import annotations

from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision


class BybitOrderManager:
    """Bybit execution adapter placeholder.

    The v7 OrderManager will be copied behind this adapter after safety patching.
    """

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        return {"ok": False, "reason": "Bybit live adapter not connected in scaffold", "symbol": asset.symbol}

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        return {"ok": False, "reason": "Bybit live adapter not connected in scaffold", "symbol": asset.symbol}

