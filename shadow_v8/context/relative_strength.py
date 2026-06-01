from __future__ import annotations


def relative_strength_ratio(symbol_returns: list[float], benchmark_returns: list[float]) -> float:
    if not symbol_returns or not benchmark_returns:
        return 0.0
    symbol_total = sum(symbol_returns)
    benchmark_total = sum(benchmark_returns)
    return symbol_total - benchmark_total

