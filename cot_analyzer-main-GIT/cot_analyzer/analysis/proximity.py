"""
proximity.py
COT Proximity Index — price-based proxy for COT sentiment.

Formula (applied to weekly closing price, same as LW_Index):
    price_lw  = (close - min_N) / (max_N - min_N) × 100

Since Commercials are structurally contrarian to price direction:
    prox_comm = 100 - price_lw   (inverted — low price = Commercials bullish)
    prox_lrg  = price_lw         (Large Specs follow the trend)
    prox_sml  = price_lw         (Small Specs also trend-follow)

Useful during the 3-day window between Tuesday's COT cutoff and
Friday's CFTC release when fresh COT data is unavailable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _lw_on_price(close: pd.Series, lookback: int) -> pd.Series:
    """Apply LW_Index min-max normalization to a price series."""
    rolling_min = close.rolling(lookback, min_periods=lookback).min()
    rolling_max = close.rolling(lookback, min_periods=lookback).max()
    rng = rolling_max - rolling_min
    result = (close - rolling_min).div(rng.replace(0, np.nan)) * 100.0
    return result.fillna(50.0).clip(0.0, 100.0)


def compute_proximity(
    df_cot: pd.DataFrame,
    df_price: pd.DataFrame,
    lookback: int,
) -> pd.DataFrame:
    """
    Merge weekly price data onto the COT DataFrame and compute proximity columns.

    Parameters
    ----------
    df_cot   : enriched COT DataFrame with a 'date' column
    df_price : weekly OHLCV DataFrame with 'date' and 'close' columns
    lookback : weeks for the price range calculation

    Returns
    -------
    df_cot copy with three new columns added:
        prox_comm  — commercial proxy (inverted price LW index)
        prox_lrg   — large spec proxy (price LW index)
        prox_sml   — small spec proxy (price LW index)

    If price data is missing or too short, columns are filled with NaN.
    """
    out = df_cot.copy()

    if df_price.empty or "close" not in df_price.columns:
        out["prox_comm"] = np.nan
        out["prox_lrg"]  = np.nan
        out["prox_sml"]  = np.nan
        return out

    # Ensure dates are comparable (strip timezone if present)
    price = df_price[["date", "close"]].copy()
    price["date"] = pd.to_datetime(price["date"]).dt.tz_localize(None)
    cot_dates     = pd.to_datetime(out["date"]).dt.tz_localize(None)

    # Sort and compute the LW index on the full price series first
    price = price.sort_values("date").reset_index(drop=True)
    price["price_lw"] = _lw_on_price(price["close"], lookback)

    # Align: for each COT date find the nearest prior price bar (as-of join)
    price_idx = pd.Series(
        price["price_lw"].values,
        index=price["date"],
    )
    aligned = price_idx.reindex(cot_dates, method="ffill").values

    price_lw_aligned = pd.Series(aligned, index=out.index)

    out["prox_comm"] = (100.0 - price_lw_aligned).clip(0.0, 100.0)
    out["prox_lrg"]  = price_lw_aligned.clip(0.0, 100.0)
    out["prox_sml"]  = price_lw_aligned.clip(0.0, 100.0)

    return out
