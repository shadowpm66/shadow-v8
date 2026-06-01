from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from shadow_v8.models import AssetConfig, BrokerConfig, ScannerConfig


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


PATHS = {
    "state": ROOT_DIR / "runtime" / "state.json",
    "positions": ROOT_DIR / "runtime" / "positions.json",
    "closed_trades": ROOT_DIR / "runtime" / "closed_trades.json",
    "dashboard": ROOT_DIR / "runtime" / "dashboard",
    "dashboard_scan": ROOT_DIR / "runtime" / "dashboard" / "scanner_results.json",
    "dashboard_latest": ROOT_DIR / "runtime" / "dashboard" / "latest_snapshot.json",
    "dashboard_risk": ROOT_DIR / "runtime" / "dashboard" / "risk_status.json",
    "dashboard_decisions": ROOT_DIR / "runtime" / "dashboard" / "recent_decisions.json",
    "dashboard_status": ROOT_DIR / "runtime" / "dashboard" / "engine_status.json",
    "logs": ROOT_DIR / "logs",
    "daily_logs": ROOT_DIR / "logs" / "daily",
    "research": ROOT_DIR / "logs" / "research.jsonl",
}


BROKERS = {
    "bybit": BrokerConfig(
        name="bybit",
        enabled=os.getenv("BYBIT_ENABLED", "true").lower() in ("1", "true", "on", "yes"),
        paper=os.getenv("BYBIT_PAPER", "false").lower() in ("1", "true", "on", "yes"),
        base_url=os.getenv("BASE_URL", "https://api.bybit.com"),
    ),
    "ibkr": BrokerConfig(
        name="ibkr",
        enabled=os.getenv("IBKR_ENABLED", "false").lower() in ("1", "true", "on", "yes"),
        paper=os.getenv("IBKR_PAPER", "true").lower() in ("1", "true", "on", "yes"),
        account_id=os.getenv("IBKR_ACCOUNT_ID"),
    ),
    "paper": BrokerConfig(name="paper", enabled=True, paper=True),
}


ASSETS = [
    AssetConfig(
        symbol="ETHUSDT",
        asset_class="crypto",
        broker="bybit",
        enabled=True,
        primary_timeframe="15",
        confirmation_timeframe="D",
        intraday_timeframes=("15", "60", "240"),
        allow_long=True,
        allow_short=True,
        fundamentals_required=False,
        max_risk_pct=0.03,
        tags=("default_crypto",),
    ),
    AssetConfig(
        symbol="BTCUSDT",
        asset_class="crypto",
        broker="bybit",
        enabled=os.getenv("BTC_ENABLED", "false").lower() in ("1", "true", "on", "yes"),
        primary_timeframe="15",
        confirmation_timeframe="D",
        intraday_timeframes=("15", "60", "240"),
        allow_long=True,
        allow_short=True,
        fundamentals_required=False,
        max_risk_pct=0.03,
        tags=("crypto",),
    ),
]


SCANNER_CONFIG = ScannerConfig(
    enabled=True,
    asset_classes=("stock",),
    min_price=float(os.getenv("STOCK_MIN_PRICE", "5")),
    min_avg_dollar_volume=float(os.getenv("STOCK_MIN_AVG_DOLLAR_VOLUME", "20000000")),
    require_fundamentals=True,
    max_results=int(os.getenv("STOCK_SCANNER_MAX_RESULTS", "200")),
)

CRYPTO_SCAN_SYMBOLS = tuple(
    s.strip().upper()
    for s in os.getenv("CRYPTO_SCAN_SYMBOLS", "ETHUSDT,BTCUSDT,SOLUSDT,BNBUSDT,XRPUSDT,LINKUSDT,AVAXUSDT").split(",")
    if s.strip()
)

CRYPTO_SCAN_CONFIG = {
    "enabled": os.getenv("CRYPTO_SCAN_ENABLED", "true").lower() in ("1", "true", "on", "yes"),
    "scan_all_usdt": os.getenv("CRYPTO_SCAN_ALL_USDT", "false").lower() in ("1", "true", "on", "yes"),
    "max_symbols": int(os.getenv("CRYPTO_SCAN_MAX_SYMBOLS", "25")),
    "seed_symbols": CRYPTO_SCAN_SYMBOLS,
}


STOCK_SCAN_SYMBOLS = tuple(
    s.strip().upper()
    for s in os.getenv(
        "STOCK_SCAN_SYMBOLS",
        "NVDA,MSFT,AMZN,META,AVGO,LLY,TSLA,PLTR,CRWD,ANET,SMCI",
    ).split(",")
    if s.strip()
)

STOCK_SCAN_CONFIG = {
    "enabled": os.getenv("STOCK_SCAN_ENABLED", "true").lower() in ("1", "true", "on", "yes"),
    "max_symbols": int(os.getenv("STOCK_SCAN_MAX_SYMBOLS", "25")),
    "seed_symbols": STOCK_SCAN_SYMBOLS,
    "allow_short": os.getenv("STOCK_SHORTS_ENABLED", "false").lower() in ("1", "true", "on", "yes"),
    "paper_entries_enabled": os.getenv("STOCK_PAPER_ENTRIES_ENABLED", "false").lower()
    in ("1", "true", "on", "yes"),
    "default_risk_pct": float(os.getenv("STOCK_NORMAL_MAX_ACCOUNT_RISK_PCT", "0.015")),
}


STOCK_MARKET_DATA_CONFIG = {
    "source": os.getenv("STOCK_MARKET_DATA_SOURCE", "stooq").lower(),
    "timeout_sec": float(os.getenv("STOCK_MARKET_DATA_TIMEOUT_SEC", "10")),
    "stooq_suffix": os.getenv("STOOQ_SUFFIX", "us").strip().lower(),
}


RISK_CONFIG = {
    "max_open_positions_total": int(os.getenv("MAX_OPEN_POSITIONS_TOTAL", "3")),
    "max_open_crypto_positions": int(os.getenv("MAX_OPEN_CRYPTO_POSITIONS", "1")),
    "max_open_stock_positions": int(os.getenv("MAX_OPEN_STOCK_POSITIONS", "3")),
    "daily_r_limit": float(os.getenv("DAILY_R_LIMIT", "-2.0")),
    "stock_normal_max_account_risk_pct": float(os.getenv("STOCK_NORMAL_MAX_ACCOUNT_RISK_PCT", "0.015")),
    "stock_ideal_stop_min_pct": float(os.getenv("STOCK_IDEAL_STOP_MIN_PCT", "2.5")),
    "stock_ideal_stop_max_pct": float(os.getenv("STOCK_IDEAL_STOP_MAX_PCT", "5.0")),
    "stock_max_position_pct": float(os.getenv("STOCK_MAX_POSITION_PCT", "0.25")),
    "default_crypto_risk_pct": float(os.getenv("DEFAULT_CRYPTO_RISK_PCT", "0.03")),
}


ENGINE_CONFIG = {
    "scan_interval_sec": int(os.getenv("SCAN_INTERVAL_SEC", "300")),
    "run_once": os.getenv("SHADOW_RUN_ONCE", "false").lower() in ("1", "true", "on", "yes"),
}


EXECUTION_CONFIG = {
    "mode": os.getenv("SHADOW_EXECUTION_MODE", "scan_only").lower(),
    "paper_account_balance": float(os.getenv("PAPER_ACCOUNT_BALANCE", "10000")),
    "paper_take_profit_r": float(os.getenv("PAPER_TAKE_PROFIT_R", "2.0")),
    "paper_partial_r": float(os.getenv("PAPER_PARTIAL_R", "1.0")),
    "paper_partial_fraction": float(os.getenv("PAPER_PARTIAL_FRACTION", "0.40")),
    "paper_break_even_r": float(os.getenv("PAPER_BREAK_EVEN_R", "1.2")),
    "paper_trail_start_r": float(os.getenv("PAPER_TRAIL_START_R", "3.0")),
    "paper_trail_giveback_r": float(os.getenv("PAPER_TRAIL_GIVEBACK_R", "1.0")),
    "min_stop_pct": float(os.getenv("MIN_STOP_PCT", "0.01")),
}


TELEGRAM_CONFIG = {
    "alerts_enabled": os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() in ("1", "true", "on", "yes"),
    "top_setup_min_score": float(os.getenv("TELEGRAM_TOP_SETUP_MIN_SCORE", "45")),
    "top_setup_cooldown_sec": int(os.getenv("TELEGRAM_TOP_SETUP_COOLDOWN_SEC", "3600")),
    "monitor_cooldown_sec": int(os.getenv("TELEGRAM_MONITOR_COOLDOWN_SEC", "1800")),
    "paper_entry_alerts": os.getenv("TELEGRAM_PAPER_ENTRY_ALERTS", "true").lower()
    in ("1", "true", "on", "yes"),
    "engine_warning_alerts": os.getenv("TELEGRAM_ENGINE_WARNING_ALERTS", "true").lower()
    in ("1", "true", "on", "yes"),
}


EARNINGS_RULES = {
    "avoid_new_entries_before_days": int(os.getenv("EARNINGS_BLOCK_DAYS", "5")),
    "allow_post_earnings_gap_setups": os.getenv("ALLOW_POST_EARNINGS_SETUPS", "true").lower()
    in ("1", "true", "on", "yes"),
}


FUNDAMENTALS_CONFIG = {
    "source": os.getenv("STOCK_FUNDAMENTALS_SOURCE", "demo").lower(),
    "demo_symbol": os.getenv("STOCK_FUNDAMENTALS_SYMBOL", "NVDA").strip().upper(),
    "sec_user_agent": os.getenv("SEC_USER_AGENT", "").strip(),
}


FEATURE_FLAGS = {
    "stocks_enabled": os.getenv("STOCKS_ENABLED", "true").lower() in ("1", "true", "on", "yes"),
    "stock_live_trading_enabled": os.getenv("STOCK_LIVE_TRADING_ENABLED", "false").lower()
    in ("1", "true", "on", "yes"),
    "crypto_live_trading_enabled": os.getenv("CRYPTO_LIVE_TRADING_ENABLED", "false").lower()
    in ("1", "true", "on", "yes"),
    "stock_shorts_enabled": os.getenv("STOCK_SHORTS_ENABLED", "false").lower() in ("1", "true", "on", "yes"),
    "research_logging_enabled": True,
}


def enabled_assets() -> list[AssetConfig]:
    return [asset for asset in ASSETS if asset.enabled]


def ensure_runtime_dirs() -> None:
    for key in ("logs", "daily_logs"):
        PATHS[key].mkdir(parents=True, exist_ok=True)
    PATHS["state"].parent.mkdir(parents=True, exist_ok=True)
    PATHS["dashboard"].mkdir(parents=True, exist_ok=True)
