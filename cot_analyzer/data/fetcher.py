"""
fetcher.py
Downloads CFTC COT data via the cot-reports library and caches
results locally as Parquet files.  Handles staleness checks so
the network is only hit when new data is expected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from cot_analyzer.utils.constants import COT_REPORT_TYPE_MAP
from cot_analyzer.utils.helpers import cache_is_stale

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _cache_path(cache_dir: Path, report_type: str, year: int) -> Path:
    return cache_dir / f"{report_type}_{year}.parquet"


def _load_year_from_cot_library(cot_type: str, year: int) -> pd.DataFrame:
    """Download a single year using the cot-reports library."""
    try:
        import cot_reports as cot  # type: ignore
        logger.info("Downloading %s data for %d from CFTC …", cot_type, year)
        df = cot.cot_year(year=year, cot_report_type=cot_type)
        return df
    except Exception as exc:
        logger.warning("cot-reports failed for %s/%d: %s", cot_type, year, exc)
        raise


def _save_cache(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.debug("Cached → %s", path)


def _load_cache(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def fetch_cot_data(
    report_type: str,
    years_history: int,
    cache_dir: Path,
    cache_enabled: bool,
    auto_refresh: bool,
) -> pd.DataFrame:
    """
    Return a combined DataFrame covering the requested years.

    Strategy
    --------
    For each required year:
      1. If cache file exists and is not stale → load from disk.
      2. Else download from CFTC and save to cache.

    Parameters
    ----------
    report_type   : 'Legacy' | 'Disaggregated' | 'Financial'
    years_history : number of past years to load (e.g. 5)
    cache_dir     : path to the local parquet cache directory
    cache_enabled : if False, always download fresh (no caching)
    auto_refresh  : if True, re-fetch current year when stale
    """
    cot_type = COT_REPORT_TYPE_MAP.get(report_type)
    if not cot_type:
        raise ValueError(
            f"Unknown report_type: {report_type!r}. "
            f"Valid: {list(COT_REPORT_TYPE_MAP)}"
        )

    current_year = datetime.now(tz=timezone.utc).year
    years = list(range(current_year - years_history + 1, current_year + 1))

    frames: list[pd.DataFrame] = []

    for year in years:
        cache_file = _cache_path(cache_dir, cot_type, year)
        is_current_year = year == current_year

        use_cache = (
            cache_enabled
            and cache_file.exists()
            and not (is_current_year and auto_refresh and _is_stale(cache_file))
        )

        if use_cache:
            logger.debug("Cache hit  → %s", cache_file.name)
            df = _load_cache(cache_file)
        else:
            df = _load_year_from_cot_library(cot_type, year)
            if cache_enabled:
                _save_cache(df, cache_file)

        frames.append(df)

    if not frames:
        raise RuntimeError("No COT data could be loaded.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "Loaded %d rows across %d years (%s)",
        len(combined), len(years), report_type,
    )
    return combined


def _is_stale(cache_file: Path) -> bool:
    """Return True if the cached file is older than the latest CFTC release."""
    mtime = datetime.fromtimestamp(
        cache_file.stat().st_mtime, tz=timezone.utc
    )
    return cache_is_stale(mtime)
