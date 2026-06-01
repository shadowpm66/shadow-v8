from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from shadow_v8.config import (
    BROKERS,
    CRYPTO_SCAN_CONFIG,
    EARNINGS_RULES,
    ENGINE_CONFIG,
    EXECUTION_CONFIG,
    FEATURE_FLAGS,
    FUNDAMENTALS_CONFIG,
    RISK_CONFIG,
    SCANNER_CONFIG,
    STOCK_MARKET_DATA_CONFIG,
    STOCK_SCAN_CONFIG,
    TELEGRAM_CONFIG,
    enabled_assets,
    ensure_runtime_dirs,
)
from shadow_v8.context.stage_engine import StageEngine
from shadow_v8.data.bybit_market_data import BybitMarketData
from shadow_v8.data.market_data import CompositeMarketData, MarketDataProvider
from shadow_v8.data.scanner import CryptoScanner, StockScanner
from shadow_v8.data.stooq_market_data import StooqMarketData
from shadow_v8.fundamentals.earnings_calendar import EarningsCalendar
from shadow_v8.execution.paper_order_manager import PaperOrderManager
from shadow_v8.fundamentals.earnings_engine import EarningsEngine
from shadow_v8.fundamentals.growth_engine import GrowthEngine
from shadow_v8.fundamentals.sec_company_facts import SecCompanyFactsClient
from shadow_v8.fundamentals.stock_filter import StockFilter
from shadow_v8.models import (
    AssetConfig,
    Candle,
    EarningsState,
    EntryDecision,
    FundamentalState,
    MarketDataBundle,
    ResearchSnapshot,
    RiskDecision,
)
from shadow_v8.strategy.entry_policy import EntryPolicy
from shadow_v8.strategy.risk_manager import RiskManager
from shadow_v8.strategy.scorer import Scorer
from shadow_v8.structure.base_engine import BaseEngine
from shadow_v8.structure.nested_structure import NestedStructureDetector
from shadow_v8.structure.pivot_confirmation import PivotConfirmationEngine
from shadow_v8.structure.vcp_engine import VcpEngine
from shadow_v8.structure.wm_detector import WmDetector
from shadow_v8.telemetry.commands import CommandProcessor
from shadow_v8.telemetry.dashboard_writer import DashboardWriter
from shadow_v8.telemetry.telegram_alerts import TelegramAlerts
from shadow_v8.telemetry.research_logger import ResearchLogger


def _demo_candles(count: int = 120, start: float = 100.0) -> list[Candle]:
    now = datetime.now(timezone.utc)
    candles: list[Candle] = []
    price = start
    for idx in range(count):
        drift = 0.10 if idx > 40 else -0.02
        wave = ((idx % 14) - 7) * 0.06
        open_ = price
        close = max(1.0, price + drift + wave)
        high = max(open_, close) + 0.45
        low = min(open_, close) - 0.45
        volume = 1_000_000 * (0.7 if idx > 95 else 1.0)
        candles.append(
            Candle(
                timestamp=now - timedelta(days=count - idx),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        price = close
    return candles


def main() -> None:
    ensure_runtime_dirs()

    print("Shadow v8 foundation loaded.")
    print(f"Enabled assets: {[asset.symbol for asset in enabled_assets()]}")
    print(f"Stock scanner enabled: {SCANNER_CONFIG.enabled}")
    print(f"Crypto live enabled: {FEATURE_FLAGS['crypto_live_trading_enabled']}")
    print(f"Stock live enabled: {FEATURE_FLAGS['stock_live_trading_enabled']}")
    print(f"IBKR enabled: {BROKERS['ibkr'].enabled}")
    print(f"Earnings block days: {EARNINGS_RULES['avoid_new_entries_before_days']}")
    print(f"Risk config: {RISK_CONFIG}")
    print(f"Engine config: {ENGINE_CONFIG}")
    print(f"Execution config: {EXECUTION_CONFIG}")
    print(f"Telegram alerts enabled: {TELEGRAM_CONFIG['alerts_enabled']}")
    print(f"Stock market data source: {STOCK_MARKET_DATA_CONFIG['source']}")

    bybit = BybitMarketData()
    dashboard = DashboardWriter()
    paper = PaperOrderManager(account_balance=EXECUTION_CONFIG["paper_account_balance"])
    alerts = TelegramAlerts()
    commands = CommandProcessor()

    while True:
        cycle_started = datetime.now(timezone.utc)
        errors: list[str] = []
        scan_count = 0
        try:
            command_result = commands.process_once()
            if command_result.get("commands"):
                print(f"Telegram commands processed: {command_result['commands']}")
            entries_paused = commands.entries_paused()
            scan_count = len(_run_scan_cycle(bybit, dashboard, paper, alerts, entries_paused=entries_paused))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            print(f"Cycle error: {errors[-1]}")

        cycle_finished = datetime.now(timezone.utc)
        duration_sec = (cycle_finished - cycle_started).total_seconds()
        dashboard.write_status(
            cycle_started_at=cycle_started,
            cycle_finished_at=cycle_finished,
            duration_sec=duration_sec,
            scan_count=scan_count,
            mode=_engine_mode_label(),
            live_trading_enabled=_live_trading_enabled(),
            entries_paused=commands.entries_paused(),
            errors=errors,
        )
        alerts.engine_warning(errors)

        if ENGINE_CONFIG["run_once"]:
            break

        sleep_for = max(30, int(ENGINE_CONFIG["scan_interval_sec"]))
        print(f"Next scan in {sleep_for}s")
        _sleep_with_commands(sleep_for, commands)


def _run_scan_cycle(
    bybit: BybitMarketData,
    dashboard: DashboardWriter,
    paper: PaperOrderManager | None = None,
    alerts: TelegramAlerts | None = None,
    entries_paused: bool = False,
) -> list[dict]:
    crypto_assets = CryptoScanner(bybit).scan(CRYPTO_SCAN_CONFIG) or enabled_assets()
    stock_assets = StockScanner().scan(STOCK_SCAN_CONFIG) if FEATURE_FLAGS["stocks_enabled"] else []
    print(f"Crypto scan universe: {[asset.symbol for asset in crypto_assets]}")
    if stock_assets:
        print(f"Stock scan universe: {[asset.symbol for asset in stock_assets]}")

    stock_market = _stock_market_provider() if stock_assets else None
    crypto_results = [_evaluate_asset(asset, bybit) for asset in crypto_assets]
    stock_results = [_evaluate_stock_asset(asset, bybit, stock_market) for asset in stock_assets]
    scan_results = crypto_results + stock_results
    scan_results.sort(key=lambda item: item["setup"].final_score, reverse=True)
    if paper is not None and EXECUTION_CONFIG["mode"] == "paper":
        lifecycle_events = paper.manage_positions(_paper_market_ranges(scan_results))
        for event in lifecycle_events:
            print(f"Paper lifecycle: {event['symbol']} {event['type']} reason={event['reason']}")
            if alerts is not None:
                alerts.paper_lifecycle(event)
        _sync_paper_positions(scan_results, paper)
        paper_candidates = _paper_entry_candidates(scan_results)
        execution_results = [] if entries_paused else _process_paper_entries(paper_candidates, paper)
        for result in execution_results:
            print(f"Paper execution: {result['symbol']} ok={result['ok']} reason={result['reason']}")
            if alerts is not None:
                alerts.paper_execution(result)
        _sync_paper_positions(scan_results, paper)
    dashboard.write_scan(scan_results)
    dashboard.write_risk(scan_results)
    if alerts is not None:
        alerts.scan_summary(scan_results)

    print("Market scan results:")
    for rank, result in enumerate(scan_results, start=1):
        setup = result["setup"]
        stage = result["stage"]
        base = result["base"]
        vcp = result["vcp"]
        structure = result["structure"]
        pivot = result["pivot"]
        entry = result["entry"]
        market = result["market"]
        print(
            f"{rank}. {setup.symbol} ({result['asset'].asset_class}) action={entry.action} grade={setup.grade} "
            f"score={setup.final_score:.1f} weekly={stage.weekly_stage.value} "
            f"daily={stage.daily_stage.value} base={base.quality_score:.1f} "
            f"vcp={vcp.tightness_score:.1f} structure={structure.type}/{structure.quality_score:.1f} "
            f"pivot={pivot.confirmed} last={market.last_price} source={market.metadata.get('source')}"
        )
    print("Dashboard data written: runtime/dashboard/scanner_results.json")
    print("Dashboard data written: runtime/dashboard/latest_snapshot.json")
    print("Dashboard data written: runtime/dashboard/risk_status.json")
    return scan_results


def _sleep_with_commands(seconds: int, commands: CommandProcessor) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            result = commands.process_once()
            if result.get("commands"):
                print(f"Telegram commands processed: {result['commands']}")
        except Exception as exc:
            print(f"Telegram command error: {type(exc).__name__}: {exc}")
        time.sleep(min(5, max(0.0, deadline - time.time())))


def _stock_market_provider() -> MarketDataProvider | None:
    source = STOCK_MARKET_DATA_CONFIG["source"]
    if source == "stooq":
        return StooqMarketData(
            suffix=STOCK_MARKET_DATA_CONFIG["stooq_suffix"],
            timeout_sec=STOCK_MARKET_DATA_CONFIG["timeout_sec"],
        )
    if source in ("", "off", "demo"):
        return None
    print(f"Unknown stock market data source {source!r}; using demo fallback.")
    return None


def _load_stock_fundamentals(symbol: str | None = None) -> tuple[str, FundamentalState]:
    requested_symbol = (symbol or FUNDAMENTALS_CONFIG["demo_symbol"] or "NVDA").strip().upper()
    if FUNDAMENTALS_CONFIG["source"] == "sec":
        try:
            inputs = SecCompanyFactsClient().get_growth_inputs(requested_symbol)
            fundamentals = GrowthEngine().evaluate(
                revenue=inputs.revenue,
                eps=inputs.eps,
                gross_margin=inputs.gross_margin,
                operating_margin=inputs.operating_margin,
                free_cash_flow=inputs.free_cash_flow,
            )
            print(
                f"SEC fundamentals loaded: {inputs.symbol} cik={inputs.cik} "
                f"revenue_q={len(inputs.revenue)} eps_q={len(inputs.eps)} "
                f"grade={fundamentals.fundamental_grade}"
            )
            return inputs.symbol, fundamentals
        except Exception as exc:
            print(f"SEC fundamentals unavailable for {requested_symbol}: {type(exc).__name__}: {exc}")
            if symbol:
                return requested_symbol, FundamentalState(
                    fundamental_grade="UNKNOWN",
                    reasons=[f"SEC fundamentals unavailable: {type(exc).__name__}: {exc}"],
                )
    return requested_symbol, GrowthEngine().evaluate(
        revenue=[100, 110, 121, 135, 160, 190, 235, 300],
        eps=[0.20, 0.24, 0.29, 0.35, 0.48, 0.70, 1.05, 1.60],
        gross_margin=[48, 49, 50, 52, 53, 55],
        operating_margin=[12, 13, 15, 17, 19, 22],
        free_cash_flow=[5, 8, 11, 18],
    )


def _load_stock_earnings(symbol: str) -> EarningsState:
    try:
        next_date = EarningsCalendar().next_earnings_date(symbol)
        return EarningsEngine().evaluate(next_date=next_date)
    except Exception as exc:
        return EarningsState(reasons=[f"Earnings calendar unavailable: {type(exc).__name__}: {exc}"])


def _engine_mode_label() -> str:
    mode = EXECUTION_CONFIG["mode"]
    if mode == "paper":
        return "paper"
    if mode == "live_guarded" and _live_trading_enabled():
        return "live-guarded"
    return "scan-only"


def _live_trading_enabled() -> bool:
    if EXECUTION_CONFIG["mode"] != "live_guarded":
        return False
    return FEATURE_FLAGS["crypto_live_trading_enabled"] or FEATURE_FLAGS["stock_live_trading_enabled"]


def _sync_paper_positions(scan_results: list[dict], paper: PaperOrderManager) -> None:
    prices = {}
    for result in scan_results:
        price = _current_price(result)
        if price is not None:
            prices[result["asset"].symbol] = price
    paper.mark_to_market(prices)


def _paper_market_ranges(scan_results: list[dict]) -> dict[str, dict[str, float]]:
    ranges = {}
    for result in scan_results:
        market = result["market"]
        symbol = result["asset"].symbol
        daily = market.candles.get("D") or []
        last = _current_price(result)
        if daily:
            candle = daily[-1]
            ranges[symbol] = {
                "high": float(candle.high),
                "low": float(candle.low),
                "last": float(last if last is not None else candle.close),
            }
        elif last is not None:
            ranges[symbol] = {"high": float(last), "low": float(last), "last": float(last)}
    return ranges


def _paper_entry_candidates(scan_results: list[dict]) -> list[dict]:
    candidates = [result for result in scan_results if result["entry"].action == "ENTER"]
    return sorted(candidates, key=lambda item: item["setup"].final_score, reverse=True)


def _process_paper_entries(scan_results: list[dict], paper: PaperOrderManager) -> list[dict]:
    results = []
    open_count = len(paper.store.load_all())
    for result in scan_results:
        if open_count >= RISK_CONFIG["max_open_positions_total"]:
            break
        entry = result["entry"]
        if entry.action != "ENTER":
            continue
        prepared = _prepare_paper_entry(result)
        if prepared is None:
            continue
        execution = paper.enter(result["asset"], prepared)
        results.append(execution)
        if execution.get("ok"):
            open_count += 1
    return results


def _prepare_paper_entry(result: dict) -> EntryDecision | None:
    entry = result["entry"]
    setup = result["setup"]
    risk = result["risk"]
    price = _current_price(result)
    if price is None or setup.direction == "FLAT":
        return None
    stop = _paper_stop(result, price)
    if stop is None:
        return None
    target = _paper_target(setup.direction, price, stop)
    entry.entry = round(price, 8)
    entry.stop = round(stop, 8)
    entry.target = round(target, 8) if target is not None else None
    entry.metadata.update(
        {
            "risk_pct": risk.risk_pct,
            "risk_state": risk.state,
            "risk_reason": risk.reason,
            "setup_score": setup.final_score,
            "paper_prepared": True,
            **risk.metadata,
        }
    )
    return entry


def _current_price(result: dict) -> float | None:
    market = result["market"]
    if market.last_price is not None:
        return float(market.last_price)
    daily = market.candles.get("D") or []
    if daily:
        return float(daily[-1].close)
    structure = result["structure"]
    if structure.entry is not None:
        return float(structure.entry)
    return None


def _paper_stop(result: dict, entry: float) -> float | None:
    setup = result["setup"]
    base = result["base"]
    structure = result["structure"]
    market = result["market"]
    daily = market.candles.get("D") or []
    min_stop_pct = EXECUTION_CONFIG["min_stop_pct"]
    if setup.direction == "LONG":
        candidates = [value for value in (base.low, structure.base, daily[-1].low if daily else None) if value is not None and value < entry]
        stop = max(candidates) if candidates else entry * (1.0 - min_stop_pct)
        if (entry - stop) / max(entry, 1e-9) < min_stop_pct:
            stop = entry * (1.0 - min_stop_pct)
        return stop
    if setup.direction == "SHORT":
        candidates = [value for value in (base.high, structure.base, daily[-1].high if daily else None) if value is not None and value > entry]
        stop = min(candidates) if candidates else entry * (1.0 + min_stop_pct)
        if (stop - entry) / max(entry, 1e-9) < min_stop_pct:
            stop = entry * (1.0 + min_stop_pct)
        return stop
    return None


def _paper_target(direction: str, entry: float, stop: float) -> float | None:
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    multiple = EXECUTION_CONFIG["paper_take_profit_r"]
    if direction == "LONG":
        return entry + risk * multiple
    if direction == "SHORT":
        return entry - risk * multiple
    return None


def _evaluate_stock_asset(
    asset: AssetConfig,
    bybit: BybitMarketData,
    stock_provider: MarketDataProvider | None = None,
) -> dict:
    market = _load_market_data(asset, bybit, stock_provider)
    daily = market.candles.get("D") or _demo_candles()
    weekly = market.candles.get("W") or _demo_candles(count=80, start=80.0)
    stage = StageEngine().evaluate(weekly=weekly, daily=daily)
    structure = WmDetector().detect(daily)
    base_direction = structure.direction if structure.direction != "FLAT" else "LONG"
    base = BaseEngine().evaluate(daily, direction=base_direction)
    vcp = VcpEngine().evaluate(daily, pivot=base.pivot)
    nested = NestedStructureDetector().detect(daily)
    pivot = PivotConfirmationEngine().evaluate(daily, base.pivot, structure.direction)
    fundamentals_symbol, fundamentals = _load_stock_fundamentals(asset.symbol)
    earnings = _load_stock_earnings(asset.symbol)
    setup = Scorer().score(
        asset.symbol,
        stage,
        base,
        vcp,
        structure,
        nested,
        pivot,
        fundamentals=fundamentals,
        earnings=earnings,
    )

    approved, filter_reasons = StockFilter().approve(fundamentals, earnings, stage, setup)
    setup.metadata.update(
        {
            "fundamentals_symbol": fundamentals_symbol,
            "stock_filter_approved": approved,
            "stock_filter_reasons": filter_reasons,
        }
    )
    for reason in filter_reasons:
        if reason not in setup.reasons:
            setup.reasons.append(reason)

    if approved:
        risk = RiskManager().evaluate(asset, setup)
        entry = EntryPolicy().decide(asset, setup, risk)
    else:
        reason = "; ".join(filter_reasons) if filter_reasons else "Stock filter rejected setup"
        risk = RiskDecision(state="OFF", risk_pct=0.0, reason=reason)
        entry = EntryDecision(action="SKIP", symbol=asset.symbol, direction=setup.direction, reason=reason, setup=setup)

    entry.metadata.update(
        {
            "fundamentals_symbol": fundamentals_symbol,
            "fundamental_grade": fundamentals.fundamental_grade,
            "earnings_blocked": earnings.blocked_for_earnings,
            "stock_filter_approved": approved,
        }
    )

    ResearchLogger().record(
        ResearchSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            stage=stage,
            base=base,
            vcp=vcp,
            structure=structure,
            nested_structure=nested,
            pivot_confirmation=pivot,
            fundamentals=fundamentals,
            earnings=earnings,
            setup=setup,
            entry_decision=entry,
            risk_decision=risk,
        )
    )
    return {
        "asset": asset,
        "market": market,
        "stage": stage,
        "base": base,
        "vcp": vcp,
        "structure": structure,
        "nested": nested,
        "pivot": pivot,
        "fundamentals": fundamentals,
        "earnings": earnings,
        "setup": setup,
        "risk": risk,
        "entry": entry,
        "stock_filter": {"approved": approved, "reasons": filter_reasons},
    }


def _evaluate_asset(asset: AssetConfig, bybit: BybitMarketData) -> dict:
    market = _load_market_data(asset, bybit)
    daily = market.candles.get("D") or _demo_candles()
    weekly = market.candles.get("W") or _demo_candles(count=80, start=80.0)
    stage = StageEngine().evaluate(weekly=weekly, daily=daily)
    structure = WmDetector().detect(daily)
    base_direction = structure.direction if structure.direction != "FLAT" else "LONG"
    base = BaseEngine().evaluate(daily, direction=base_direction)
    vcp = VcpEngine().evaluate(daily, pivot=base.pivot)
    nested = NestedStructureDetector().detect(daily)
    pivot = PivotConfirmationEngine().evaluate(daily, base.pivot, structure.direction)
    setup = Scorer().score(asset.symbol, stage, base, vcp, structure, nested, pivot)
    risk = RiskManager().evaluate(asset, setup)
    entry = EntryPolicy().decide(asset, setup, risk)

    ResearchLogger().record(
        ResearchSnapshot(
            timestamp=datetime.now(timezone.utc),
            symbol=asset.symbol,
            asset_class=asset.asset_class,
            stage=stage,
            base=base,
            vcp=vcp,
            structure=structure,
            nested_structure=nested,
            pivot_confirmation=pivot,
            setup=setup,
            entry_decision=entry,
            risk_decision=risk,
        )
    )
    return {
        "asset": asset,
        "market": market,
        "stage": stage,
        "base": base,
        "vcp": vcp,
        "structure": structure,
        "nested": nested,
        "pivot": pivot,
        "setup": setup,
        "risk": risk,
        "entry": entry,
    }


def _load_market_data(
    asset: AssetConfig,
    bybit: BybitMarketData | None = None,
    stock_provider: MarketDataProvider | None = None,
) -> MarketDataBundle:
    if asset.asset_class == "stock" and stock_provider is not None:
        try:
            bundle = stock_provider.load(asset)
            if bundle.candles.get("D") and bundle.candles.get("W"):
                return bundle
            fallback = _demo_market_bundle(asset)
            fallback.metadata["source"] = f"demo_fallback_empty_{bundle.metadata.get('source', 'stock')}"
            fallback.metadata["market_data_error"] = bundle.metadata.get("error") or bundle.metadata.get("status")
            return fallback
        except Exception as exc:
            fallback = _demo_market_bundle(asset)
            fallback.metadata["source"] = f"demo_fallback_stock_error:{type(exc).__name__}"
            fallback.metadata["market_data_error"] = str(exc)
            return fallback

    if asset.broker != "bybit":
        return _demo_market_bundle(asset)
    provider = CompositeMarketData({"bybit": bybit or BybitMarketData()})
    try:
        bundle = provider.load(asset)
        if bundle.candles.get("D") and bundle.candles.get("W"):
            bundle.metadata["source"] = "bybit"
            return bundle
        if not bundle.candles.get("D"):
            bundle.candles["D"] = _demo_candles()
        if not bundle.candles.get("W"):
            bundle.candles["W"] = _demo_candles(count=80, start=80.0)
        bundle.metadata["source"] = "demo_fallback_empty_bybit"
        return bundle
    except Exception as exc:
        bundle = _demo_market_bundle(asset)
        bundle.metadata["source"] = f"demo_fallback_bybit_error:{type(exc).__name__}"
        return bundle


def _demo_market_bundle(asset: AssetConfig) -> MarketDataBundle:
    return MarketDataBundle(
        symbol=asset.symbol,
        asset_class=asset.asset_class,
        candles={"D": _demo_candles(), "W": _demo_candles(count=80, start=80.0)},
        last_price=None,
        metadata={"source": "demo"},
    )


if __name__ == "__main__":
    main()
