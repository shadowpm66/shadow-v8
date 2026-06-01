from __future__ import annotations

from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision


class IbkrOrderManager:
    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        return {"ok": False, "reason": "IBKR adapter disabled until Gateway is configured", "symbol": asset.symbol}

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        return {"ok": False, "reason": "IBKR adapter disabled until Gateway is configured", "symbol": asset.symbol}

