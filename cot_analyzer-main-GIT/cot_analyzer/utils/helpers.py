"""
helpers.py
Pure utility functions: smoothing, index calculations,
percentile rank, date helpers.  No I/O, no side effects.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────
# SMOOTHING
# ─────────────────────────────────────────────────────────────

def smooth(series: pd.Series, method: str, period: int) -> pd.Series:
    """Apply moving average smoothing to a Series."""
    if method == "None" or period <= 1:
        return series
    if method == "SMA":
        return series.rolling(window=period, min_periods=1).mean()
    if method == "EMA":
        return series.ewm(span=period, adjust=False).mean()
    if method == "WMA":
        weights = np.arange(1, period + 1, dtype=float)
        return series.rolling(window=period, min_periods=1).apply(
            lambda x: np.dot(x, weights[-len(x):]) / weights[-len(x):].sum(),
            raw=True,
        )
    if method == "RMA":
        # Wilder's smoothing (used in RSI)
        return series.ewm(alpha=1.0 / period, adjust=False).mean()
    raise ValueError(f"Unknown smoothing method: {method!r}. "
                     f"Valid options: None, SMA, EMA, WMA, RMA")


# ─────────────────────────────────────────────────────────────
# INDEX CALCULATIONS
# ─────────────────────────────────────────────────────────────

def willco_index(
    net: pd.Series,
    oi: pd.Series,
    lookback: int,
) -> pd.Series:
    """
    Larry Williams OI-adjusted COT Index (WillCo).

    Step 1 — normalise by Open Interest to remove market-size distortion:
        willco_raw = (net / oi) * 100

    Step 2 — apply standard min-max normalisation over lookback window:
        willco = (willco_raw - min) / (max - min) * 100

    Returns 0–100 (50 when range is zero).
    """
    raw = net.div(oi.replace(0, np.nan)) * 100.0
    rolling_min = raw.rolling(lookback, min_periods=lookback).min()
    rolling_max = raw.rolling(lookback, min_periods=lookback).max()
    rng = rolling_max - rolling_min
    result = (raw - rolling_min).div(rng.replace(0, np.nan)) * 100.0
    return result.fillna(50.0).clip(0.0, 100.0)


def lw_index(net: pd.Series, lookback: int) -> pd.Series:
    """
    Standard Larry Williams COT Index — raw net positions,
    includes current bar in range, always 0–100.
    """
    rolling_min = net.rolling(lookback, min_periods=lookback).min()
    rolling_max = net.rolling(lookback, min_periods=lookback).max()
    rng = rolling_max - rolling_min
    result = (net - rolling_min).div(rng.replace(0, np.nan)) * 100.0
    return result.fillna(50.0).clip(0.0, 100.0)


def percentile_index(net: pd.Series, lookback: int) -> pd.Series:
    """
    tradeviZion Percentile method — excludes current bar from range.
    Can exceed 0–100 when current value breaks historical range.
    """
    shifted = net.shift(1)
    rolling_min = shifted.rolling(lookback, min_periods=lookback).min()
    rolling_max = shifted.rolling(lookback, min_periods=lookback).max()
    rng = rolling_max - rolling_min
    result = (net - rolling_min).div(rng.replace(0, np.nan)) * 100.0
    # Clamp at -20 / +120 for readability (tradeviZion V2 convention)
    return result.fillna(50.0).clip(-20.0, 120.0)


def compute_index(
    net: pd.Series,
    oi: pd.Series,
    method: str,
    lookback: int,
) -> pd.Series:
    """Dispatcher — returns the correct index series for the chosen method."""
    if method == "WillCo":
        return willco_index(net, oi, lookback)
    if method == "LW_Index":
        return lw_index(net, lookback)
    if method == "Percentile":
        return percentile_index(net, lookback)
    raise ValueError(f"Unknown analysis_method: {method!r}. "
                     f"Valid: WillCo, LW_Index, Percentile")


# ─────────────────────────────────────────────────────────────
# HISTORICAL PERCENTILE RANK
# ─────────────────────────────────────────────────────────────

def percentile_rank(series: pd.Series, lookback_rows: int) -> float:
    """
    Return where the latest value ranks (0–100 %) within the last
    `lookback_rows` observations.  NaN if not enough data.
    """
    if len(series) < 2:
        return float("nan")
    window = series.iloc[-lookback_rows:] if lookback_rows > 0 else series
    current = series.iloc[-1]
    if window.isna().all():
        return float("nan")
    rank = (window < current).sum() / len(window) * 100.0
    return round(float(rank), 1)


# ─────────────────────────────────────────────────────────────
# DATE / TIME HELPERS
# ─────────────────────────────────────────────────────────────

def latest_cftc_release() -> datetime:
    """
    Return the datetime of the most recent CFTC publication.
    CFTC publishes every Friday at 15:30 ET (20:30 UTC).
    """
    now_utc = datetime.now(tz=timezone.utc)
    # Walk back to the most recent Friday
    days_since_friday = (now_utc.weekday() - 4) % 7  # Monday=0, Friday=4
    last_friday = now_utc - timedelta(days=days_since_friday)
    release = last_friday.replace(hour=20, minute=30, second=0, microsecond=0)
    if now_utc < release:
        release -= timedelta(weeks=1)
    return release


def cache_is_stale(cache_mtime: datetime) -> bool:
    """
    Return True if the local cache predates the latest CFTC publication.
    cache_mtime must be timezone-aware (UTC).
    """
    return cache_mtime < latest_cftc_release()


def weeks_to_rows(weeks: int, trading_days_mode: str = "Weekdays") -> int:
    """Convert a week count to an approximate row count in weekly COT data."""
    # COT data is already at weekly frequency (one row per week)
    return weeks


def period_label_to_weeks(label: str) -> int:
    """Convert a period label ('1M', '3M', '6M', '1Y', '3Y', 'All') to weeks."""
    mapping = {"1M": 4, "3M": 13, "6M": 26, "1Y": 52, "3Y": 156, "All": 0}
    if label not in mapping:
        raise ValueError(f"Unknown period label: {label!r}. Valid: {list(mapping)}")
    return mapping[label]


# ─────────────────────────────────────────────────────────────
# MISC
# ─────────────────────────────────────────────────────────────

def format_contracts(value: float) -> str:
    """Human-readable contract count: 1_234_567 → '1.23M'."""
    if pd.isna(value):
        return "—"
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.2f}M"
    if abs_v >= 1_000:
        return f"{sign}{abs_v / 1_000:.1f}K"
    return f"{sign}{abs_v:.0f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Format a float as a percentage string."""
    if pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}%"
