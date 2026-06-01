from __future__ import annotations

from datetime import datetime, timezone

from shadow_v8.config import EARNINGS_RULES
from shadow_v8.models import EarningsState


class EarningsEngine:
    def evaluate(
        self,
        next_date: datetime | None,
        latest_surprise_pct: float | None = None,
        latest_report_date: datetime | None = None,
    ) -> EarningsState:
        if next_date is None:
            return EarningsState(latest_surprise_pct=latest_surprise_pct, reasons=["No earnings date available"])
        now = datetime.now(timezone.utc)
        if next_date.tzinfo is None:
            next_date = next_date.replace(tzinfo=timezone.utc)
        if latest_report_date and latest_report_date.tzinfo is None:
            latest_report_date = latest_report_date.replace(tzinfo=timezone.utc)
        days = (next_date.date() - now.date()).days
        block_days = EARNINGS_RULES["avoid_new_entries_before_days"]
        blocked = 0 <= days <= block_days
        post_earnings_setup = False
        if latest_report_date:
            days_since_report = (now.date() - latest_report_date.date()).days
            post_earnings_setup = 0 <= days_since_report <= 15 and (latest_surprise_pct or 0.0) >= 5.0
        return EarningsState(
            next_earnings_date=next_date,
            days_until_earnings=days,
            blocked_for_earnings=blocked,
            latest_surprise_pct=latest_surprise_pct,
            post_earnings_setup=post_earnings_setup,
            reasons=[
                f"{days} days until earnings",
                "Blocked before earnings" if blocked else "No earnings block",
                "Positive post-earnings setup" if post_earnings_setup else "No post-earnings setup tag",
            ],
        )
