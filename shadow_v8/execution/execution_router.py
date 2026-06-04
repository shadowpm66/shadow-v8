from __future__ import annotations

from typing import Protocol

from shadow_v8.models import AssetConfig, BrokerConfig, EntryDecision, ExitDecision


class BrokerExecutor(Protocol):
    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict: ...

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict: ...


class ExecutionRouter:
    def __init__(
        self,
        executors: dict[str, BrokerExecutor],
        *,
        mode: str = "scan_only",
        broker_configs: dict[str, BrokerConfig] | None = None,
        live_trading_enabled: dict[str, bool] | None = None,
    ) -> None:
        self.executors = executors
        self.mode = mode.lower().strip()
        self.broker_configs = broker_configs or {}
        self.live_trading_enabled = live_trading_enabled or {}

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        guard = self._guard(asset, "enter", decision.direction)
        if guard is not None:
            return guard
        executor = self.executors.get(asset.broker)
        if executor is None:
            return self._blocked(asset, "enter", f"No executor for {asset.broker}")
        return executor.enter(asset, decision)

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        guard = self._guard(asset, "exit")
        if guard is not None:
            return guard
        executor = self.executors.get(asset.broker)
        if executor is None:
            return self._blocked(asset, "exit", f"No executor for {asset.broker}")
        return executor.apply_exit(asset, decision)

    def preflight(self, asset: AssetConfig, action: str = "enter", direction: str | None = None) -> dict:
        guard = self._guard(asset, action, direction)
        executor_present = asset.broker in self.executors
        if guard is None and not executor_present:
            guard = self._blocked(asset, action, f"No executor for {asset.broker}")
        if guard is not None:
            guard["executor_present"] = executor_present
            return guard
        return {
            "ok": True,
            "symbol": asset.symbol,
            "broker": asset.broker,
            "asset_class": asset.asset_class,
            "mode": self.mode,
            "action": action,
            "direction": direction,
            "reason": "Execution preflight passed",
            "safety_block": False,
            "executor_present": True,
        }

    def _guard(self, asset: AssetConfig, action: str, direction: str | None = None) -> dict | None:
        if not asset.enabled:
            return self._blocked(asset, action, "Asset disabled")
        if direction == "LONG" and not asset.allow_long:
            return self._blocked(asset, action, "Long entries disabled for asset")
        if direction == "SHORT" and not asset.allow_short:
            return self._blocked(asset, action, "Short entries disabled for asset")
        if self.mode == "scan_only":
            return self._blocked(asset, action, "Execution mode scan_only blocks orders")
        if self.mode == "paper":
            if asset.broker != "paper":
                return self._blocked(asset, action, "Paper mode only routes paper broker orders")
            return None
        if self.mode != "live_guarded":
            return self._blocked(asset, action, f"Unknown execution mode {self.mode}")
        return self._live_guard(asset, action)

    def _live_guard(self, asset: AssetConfig, action: str) -> dict | None:
        if asset.broker == "paper":
            return self._blocked(asset, action, "Live guarded mode does not route paper broker orders")
        broker = self.broker_configs.get(asset.broker)
        if broker is None:
            return self._blocked(asset, action, f"No broker config for {asset.broker}")
        if not broker.enabled:
            return self._blocked(asset, action, f"Broker {asset.broker} disabled")
        if broker.paper:
            return self._blocked(asset, action, f"Broker {asset.broker} is configured as paper")
        if not self.live_trading_enabled.get(asset.asset_class, False):
            return self._blocked(asset, action, f"Live trading disabled for {asset.asset_class}")
        return None

    def _blocked(self, asset: AssetConfig, action: str, reason: str) -> dict:
        return {
            "ok": False,
            "symbol": asset.symbol,
            "broker": asset.broker,
            "asset_class": asset.asset_class,
            "mode": self.mode,
            "action": action,
            "reason": reason,
            "safety_block": True,
        }

