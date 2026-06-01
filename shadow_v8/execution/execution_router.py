from __future__ import annotations

from typing import Protocol

from shadow_v8.models import AssetConfig, EntryDecision, ExitDecision


class BrokerExecutor(Protocol):
    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict: ...

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict: ...


class ExecutionRouter:
    def __init__(self, executors: dict[str, BrokerExecutor]) -> None:
        self.executors = executors

    def enter(self, asset: AssetConfig, decision: EntryDecision) -> dict:
        executor = self.executors.get(asset.broker)
        if executor is None:
            return {"ok": False, "reason": f"No executor for {asset.broker}"}
        return executor.enter(asset, decision)

    def apply_exit(self, asset: AssetConfig, decision: ExitDecision) -> dict:
        executor = self.executors.get(asset.broker)
        if executor is None:
            return {"ok": False, "reason": f"No executor for {asset.broker}"}
        return executor.apply_exit(asset, decision)

