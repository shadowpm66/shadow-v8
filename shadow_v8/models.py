from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


AssetClass = Literal["crypto", "forex", "stock", "commodity", "tokenized_stock"]
Direction = Literal["LONG", "SHORT", "FLAT"]
BrokerName = Literal["bybit", "ibkr", "paper"]
OrderAction = Literal["ENTER", "WAIT", "SKIP", "MONITOR"]
ExitAction = Literal["HOLD", "EXIT", "PARTIAL", "MOVE_STOP", "FLATTEN"]


class Stage(str, Enum):
    STAGE_1 = "Stage1"
    STAGE_2 = "Stage2"
    STAGE_3 = "Stage3"
    STAGE_4 = "Stage4"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class BrokerConfig:
    name: BrokerName
    enabled: bool = True
    paper: bool = True
    base_url: str | None = None
    account_id: str | None = None


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    asset_class: AssetClass
    broker: BrokerName
    enabled: bool = True
    primary_timeframe: str = "D"
    confirmation_timeframe: str = "W"
    intraday_timeframes: tuple[str, ...] = ()
    allow_long: bool = True
    allow_short: bool = False
    fundamentals_required: bool = False
    earnings_block_days: int = 5
    max_risk_pct: float = 0.01
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScannerConfig:
    enabled: bool = True
    asset_classes: tuple[AssetClass, ...] = ("stock",)
    min_price: float = 5.0
    min_avg_dollar_volume: float = 20_000_000.0
    require_fundamentals: bool = True
    max_results: int = 200


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketDataBundle:
    symbol: str
    asset_class: AssetClass
    candles: dict[str, list[Candle]] = field(default_factory=dict)
    last_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageState:
    weekly_stage: Stage = Stage.UNKNOWN
    daily_stage: Stage = Stage.UNKNOWN
    long_weekly_compatible: bool = False
    short_weekly_compatible: bool = False
    long_daily_compatible: bool = False
    short_daily_compatible: bool = False
    long_permission: bool = False
    short_permission: bool = False
    risk_bias: Literal["RISK_ON", "NEUTRAL", "DEFENSIVE", "OFF"] = "NEUTRAL"
    reasons: list[str] = field(default_factory=list)


@dataclass
class BaseState:
    found: bool = False
    high: float | None = None
    low: float | None = None
    mid: float | None = None
    pivot: float | None = None
    duration_bars: int = 0
    depth_pct: float | None = None
    tightness_score: float = 0.0
    volume_dry_up: bool = False
    quality_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VcpState:
    is_tight: bool = False
    tightness_score: float = 0.0
    contraction_count: int = 0
    volume_dry: bool = False
    higher_lows: bool = False
    lower_highs: bool = False
    stop_distance_quality: Literal["GOOD", "ACCEPTABLE", "WIDE", "UNKNOWN"] = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructureSignal:
    type: Literal["W", "M", "NONE"] = "NONE"
    direction: Direction = "FLAT"
    entry: float | None = None
    neckline: float | None = None
    base: float | None = None
    trap: bool = False
    quality_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NestedStructureState:
    pattern: Literal["W_WITHIN_W", "M_WITHIN_M", "MIXED", "NONE"] = "NONE"
    confirmed: bool = False
    outer_structure: StructureSignal | None = None
    inner_structure: StructureSignal | None = None
    quality_score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class PivotConfirmation:
    pivot: float | None = None
    reclaimed_or_lost: bool = False
    retested: bool = False
    retest_hold: bool = False
    shift_away: bool = False
    shift_strength: float = 0.0
    confirmed: bool = False
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextState:
    quality_score: float = 0.0
    nearest_zones: list[dict[str, Any]] = field(default_factory=list)
    zone_count: int = 0
    regime: str = "range_norm"
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FundamentalState:
    revenue_growth_yoy: list[float] = field(default_factory=list)
    eps_growth_yoy: list[float] = field(default_factory=list)
    revenue_accelerating: bool = False
    eps_accelerating: bool = False
    gross_margin_expanding: bool = False
    operating_margin_expanding: bool = False
    fcf_positive: bool = False
    fundamental_grade: Literal["S", "A", "B", "C", "F", "UNKNOWN"] = "UNKNOWN"
    reasons: list[str] = field(default_factory=list)


@dataclass
class EarningsState:
    next_earnings_date: datetime | None = None
    days_until_earnings: int | None = None
    blocked_for_earnings: bool = False
    latest_surprise_pct: float | None = None
    post_earnings_setup: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class SetupDecision:
    symbol: str
    direction: Direction
    setup_class: str = "NONE"
    grade: Literal["S+", "S", "A+", "A", "B+", "B", "C", "REJECT"] = "REJECT"
    technical_score: float = 0.0
    fundamental_score: float = 0.0
    final_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EntryDecision:
    action: OrderAction
    symbol: str
    direction: Direction
    reason: str
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    setup: SetupDecision | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskDecision:
    state: Literal["FULL", "REDUCED", "DEFENSIVE", "OFF"] = "OFF"
    risk_pct: float = 0.0
    max_qty: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExitDecision:
    action: ExitAction
    symbol: str
    reason: str
    qty: float | None = None
    new_stop: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionState:
    symbol: str
    asset_class: AssetClass
    broker: BrokerName
    direction: Direction
    qty: float
    entry: float
    stop: float
    opened_at: datetime
    setup_class: str = ""
    grade: str = ""
    partial_taken: bool = False
    break_even_moved: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchSnapshot:
    timestamp: datetime
    symbol: str
    asset_class: AssetClass
    stage: StageState | None = None
    base: BaseState | None = None
    vcp: VcpState | None = None
    structure: StructureSignal | None = None
    nested_structure: NestedStructureState | None = None
    pivot_confirmation: PivotConfirmation | None = None
    context: ContextState | None = None
    fundamentals: FundamentalState | None = None
    earnings: EarningsState | None = None
    setup: SetupDecision | None = None
    entry_decision: EntryDecision | None = None
    risk_decision: RiskDecision | None = None
    notes: list[str] = field(default_factory=list)
