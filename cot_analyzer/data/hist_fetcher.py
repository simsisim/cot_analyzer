"""
hist_fetcher.py
Downloads pre-2003 CFTC COT data directly from the CFTC compressed
historical archive (https://www.cftc.gov/MarketReports/CommitmentsofTraders/
HistoricalCompressed/index.htm).

These files go back to 1986 and are plain comma-delimited .txt files
inside a zip.  The column layout is the same as modern Legacy files
except that concentration columns (Conc. Gross / Net LE 4/8 TDR) were
only added in 2004 — they are filled with NaN here.

URL patterns
------------
Futures-only  : https://www.cftc.gov/files/dea/history/deacot{YEAR}.zip
Futures+Options: https://www.cftc.gov/files/dea/history/deahistfo{YEAR}.zip
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# Columns present in modern cot-reports Legacy output that are absent
# in pre-2004 raw files (added by CFTC in 2004).
_CONCENTRATION_COLS = [
    "Conc. Gross LE 4 TDR Long",
    "Conc. Gross LE 4 TDR Short",
    "Conc. Gross LE 8 TDR Long",
    "Conc. Gross LE 8 TDR Short",
    "Conc. Net LE 4 TDR Long",
    "Conc. Net LE 4 TDR Short",
    "Conc. Net LE 8 TDR Long",
    "Conc. Net LE 8 TDR Short",
]

_BASE_URL_FO   = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
_BASE_URL_OPTS = "https://www.cftc.gov/files/dea/history/deahistfo{year}.zip"

_TIMEOUT = 60  # seconds


def _build_url(year: int, include_options: bool) -> str:
    template = _BASE_URL_OPTS if include_options else _BASE_URL_FO
    return template.format(year=year)


def _download_zip(url: str) -> bytes:
    logger.info("Downloading pre-2003 COT data from %s …", url)
    response = requests.get(url, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.content


def _parse_zip(content: bytes) -> pd.DataFrame:
    """
    Open the zip in memory, find the .txt file inside, and read it as CSV.
    Returns a raw DataFrame (columns not yet normalised).
    """
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
        if not txt_names:
            raise ValueError("No .txt file found inside the CFTC zip.")
        # Usually there is exactly one .txt file; take the first.
        with zf.open(txt_names[0]) as fh:
            df = pd.read_csv(fh, encoding="latin-1", low_memory=False)
    return df


def _fill_missing_concentration_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Add concentration columns as NaN if they are absent."""
    for col in _CONCENTRATION_COLS:
        if col not in df.columns:
            df[col] = float("nan")
    return df


def fetch_pre2003_year(
    year: int,
    include_options: bool,
    cache_dir: Path,
    cache_enabled: bool,
    cot_type: str,
) -> pd.DataFrame:
    """
    Download (or load from cache) one pre-2003 year.

    Parameters
    ----------
    year            : calendar year (must be < 2003)
    include_options : True → futures+options file; False → futures-only
    cache_dir       : directory for parquet cache
    cache_enabled   : if True, read/write parquet cache
    cot_type        : report type string used in cache filename (e.g. 'legacy_fut')

    Returns
    -------
    DataFrame with columns matching the modern cot-reports Legacy output
    (concentration columns present but filled with NaN).
    """
    cache_file = cache_dir / f"{cot_type}_{year}_hist.parquet"

    if cache_enabled and cache_file.exists():
        logger.debug("Cache hit (hist) → %s", cache_file.name)
        return pd.read_parquet(cache_file)

    url = _build_url(year, include_options)
    try:
        content = _download_zip(url)
    except requests.HTTPError as exc:
        logger.warning("HTTP error for year %d: %s — skipping.", year, exc)
        raise
    except Exception as exc:
        logger.warning("Download failed for year %d: %s — skipping.", year, exc)
        raise

    df = _parse_zip(content)
    df = _fill_missing_concentration_cols(df)

    if cache_enabled:
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_file, index=False)
        logger.debug("Cached (hist) → %s", cache_file.name)

    return df
