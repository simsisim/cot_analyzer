"""
price_fetcher.py
Downloads weekly OHLCV price data via yfinance and caches locally.
Used exclusively by the COT Proximity chart.
Failures are non-fatal — returns an empty DataFrame so the main
pipeline continues without a Proximity chart.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in ticker)
    return cache_dir / f"price_{safe}.parquet"


def fetch_price_data(
    ticker: str,
    years_history: int,
    cache_dir: Path,
    auto_refresh: bool = True,
) -> pd.DataFrame:
    """
    Return weekly OHLCV DataFrame for the given ticker.

    Columns returned: date, open, high, low, close, volume
    Sorted ascending by date.

    Falls back to empty DataFrame on any error — never raises.
    """
    if not ticker:
        return pd.DataFrame()

    cache_file = _cache_path(cache_dir, ticker)

    # Use cache if fresh enough
    if cache_file.exists() and not auto_refresh:
        try:
            return pd.read_parquet(cache_file)
        except Exception:
            pass

    if cache_file.exists() and auto_refresh:
        try:
            from cot_analyzer.utils.helpers import cache_is_stale
            import datetime
            mtime = datetime.datetime.fromtimestamp(
                cache_file.stat().st_mtime,
                tz=datetime.timezone.utc,
            )
            if not cache_is_stale(mtime):
                return pd.read_parquet(cache_file)
        except Exception:
            pass

    # Download via yfinance
    try:
        import yfinance as yf  # type: ignore
        period = f"{years_history}y"
        logger.info("Downloading price data for %s (%s) …", ticker, period)
        raw = yf.download(
            ticker,
            period=period,
            interval="1wk",
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            logger.warning("yfinance returned no data for %s", ticker)
            return pd.DataFrame()

        # Flatten multi-level columns if present (yfinance ≥0.2 returns them)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        df = raw.reset_index().rename(columns={
            "Date":   "date",
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
        df = df.sort_values("date").reset_index(drop=True)

        # Cache result
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_file, index=False)
        logger.debug("Price cache saved → %s", cache_file.name)

        return df

    except ImportError:
        logger.warning("yfinance not installed — COT Proximity chart unavailable.")
        return pd.DataFrame()
    except Exception as exc:
        logger.warning("Price fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()
