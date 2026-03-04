"""
parser.py
Filters the raw combined CFTC DataFrame down to a single instrument,
renames columns to internal short names, parses dates, and returns
a clean weekly time-series ready for the analysis layer.
"""

from __future__ import annotations

import logging

import pandas as pd

from cot_analyzer.utils.constants import (
    LEGACY_COLS,
    DISAGG_COLS,
    FINANCIAL_COLS,
)

logger = logging.getLogger(__name__)

# Columns we always want to keep (internal names)
_CORE_INTERNAL = [
    "date",
    "market_name",
    "cftc_code",
    "open_interest",
    "comm_long", "comm_short",
    "lrg_long",  "lrg_short",  "lrg_spread",
    "sml_long",  "sml_short",
    "oi_chg",
    "comm_long_chg", "comm_short_chg",
    "lrg_long_chg",  "lrg_short_chg",
    "sml_long_chg",  "sml_short_chg",
    "pct_comm_long", "pct_comm_short",
    "conc_top4_long", "conc_top4_short",
    "conc_top8_long", "conc_top8_short",
]


def _build_col_map(report_type: str) -> dict[str, str]:
    """
    Merge base Legacy column map with report-type-specific overrides.
    Returns {internal_name: raw_csv_column_name}.
    """
    base = dict(LEGACY_COLS)
    if report_type == "Disaggregated":
        base.update(DISAGG_COLS)
    elif report_type == "Financial":
        base.update(FINANCIAL_COLS)
    return base


def _normalise_code(code: str) -> str:
    """Strip whitespace and uppercase for comparison."""
    return str(code).strip().upper()


def filter_instrument(
    raw_df: pd.DataFrame,
    cftc_code: str,
    report_type: str,
) -> pd.DataFrame:
    """
    Filter raw CFTC DataFrame to a single instrument and return a
    clean, typed, date-sorted DataFrame with internal column names.

    Raises
    ------
    ValueError if the instrument is not found in the data.
    """
    col_map = _build_col_map(report_type)

    # ── 1. Find the code column (may differ by report type) ──
    code_col_candidates = [
        col_map.get("cftc_code", ""),         # resolved from report-type map
        col_map.get("commodity_code", ""),    # fallback commodity code column
        # Legacy (spaces)
        "CFTC Contract Market Code",
        "CFTC Commodity Code",
        # Disaggregated / Financial (underscores)
        "CFTC_Contract_Market_Code",
        "CFTC_Commodity_Code",
        "CFTC_Market_Code",
    ]
    code_col = next(
        (c for c in code_col_candidates if c and c in raw_df.columns),
        None,
    )
    if code_col is None:
        raise ValueError(
            "Could not locate a CFTC code column in the raw DataFrame. "
            f"Available columns: {list(raw_df.columns)[:20]}"
        )

    # ── 2. Match rows by CFTC code ────────────────────────────
    target = _normalise_code(cftc_code)
    mask   = raw_df[code_col].astype(str).str.strip().str.upper() == target
    df     = raw_df.loc[mask].copy()

    if df.empty:
        # Fallback: partial match on commodity code (handles "13874A" vs "13874+")
        base_code = target.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ+")
        mask2 = raw_df[code_col].astype(str).str.strip().str.upper().str.startswith(base_code)
        df = raw_df.loc[mask2].copy()

    if df.empty:
        raise ValueError(
            f"No data found for CFTC code {cftc_code!r}. "
            f"Check instruments.csv and ensure data_years_history covers "
            f"the desired period."
        )

    # ── 3. Rename to internal names ───────────────────────────
    rename = {}
    for internal, raw_col in col_map.items():
        if raw_col in df.columns:
            rename[raw_col] = internal

    df = df.rename(columns=rename)

    # ── 4. Parse date ─────────────────────────────────────────
    date_col = _pick_date_col(df)
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["date"])

    # ── 5. Keep only the columns we need, numeric types ───────
    keep = [c for c in _CORE_INTERNAL if c in df.columns]
    df   = df[keep].copy()

    numeric_cols = [c for c in keep if c not in ("date", "market_name", "cftc_code")]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    # ── 6. Sort and deduplicate ───────────────────────────────
    df = (
        df.sort_values("date")
          .drop_duplicates(subset=["date"], keep="last")
          .reset_index(drop=True)
    )

    logger.debug(
        "Filtered to %d weekly rows for code=%s (%s)",
        len(df), cftc_code, report_type,
    )
    return df


def _pick_date_col(df: pd.DataFrame) -> str:
    """Return the first available date column (handles Legacy spaces and Disagg underscores)."""
    candidates = [
        "date",                           # already renamed by col_map
        "As of Date in Form YYYY-MM-DD",  # Legacy (spaces)
        "As of Date in Form YYMMDD",      # Legacy (spaces)
        "Report_Date_as_YYYY-MM-DD",      # Disaggregated / Financial
        "As_of_Date_In_Form_YYMMDD",      # Disaggregated / Financial
        "As_of_Date_In_Form_MM_DD_YYYY",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"No date column found. Available: {list(df.columns)[:15]}"
    )
