"""
calculator.py
Core metric calculations: net positions, WillCo / LW / Percentile
indices, smoothing, trend analysis, OI analysis, historical ranks.
All functions are pure (no I/O); they take DataFrames and return
DataFrames or scalar results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from cot_analyzer.config.loader import AppConfig, InstrumentConfig
from cot_analyzer.utils.constants import AUTO_LOOKBACK, HISTORICAL_PERIODS
from cot_analyzer.utils.helpers import (
    smooth,
    compute_index,
    percentile_rank,
    period_label_to_weeks,
    format_contracts,
    format_pct,
)


# ─────────────────────────────────────────────────────────────
# LOOKBACK RESOLUTION
# ─────────────────────────────────────────────────────────────

def resolve_lookback(cfg: AppConfig, instrument: InstrumentConfig) -> tuple[int, int]:
    """
    Return (primary_lookback, secondary_lookback) in weeks.
    Respects per-instrument override → auto mode → manual global.
    """
    if instrument.lookback_override:
        primary = instrument.lookback_override
    elif cfg.lookback_mode == "Auto":
        primary = AUTO_LOOKBACK.get(instrument.asset_class, 26)
    else:
        primary = cfg.primary_lookback_weeks

    secondary = cfg.secondary_lookback_weeks
    return primary, secondary


# ─────────────────────────────────────────────────────────────
# NET POSITIONS
# ─────────────────────────────────────────────────────────────

def compute_net_positions(df: pd.DataFrame, smoothing_method: str, smoothing_period: int) -> pd.DataFrame:
    """
    Add net position columns (after optional smoothing).
    comm_net, lrg_net, sml_net are added in-place to a copy.
    """
    out = df.copy()
    out["comm_net_raw"] = out["comm_long"]  - out["comm_short"]
    out["lrg_net_raw"]  = out["lrg_long"]   - out["lrg_short"]
    out["sml_net_raw"]  = out["sml_long"]   - out["sml_short"]

    out["comm_net"] = smooth(out["comm_net_raw"], smoothing_method, smoothing_period)
    out["lrg_net"]  = smooth(out["lrg_net_raw"],  smoothing_method, smoothing_period)
    out["sml_net"]  = smooth(out["sml_net_raw"],  smoothing_method, smoothing_period)
    out["oi_smooth"] = smooth(out["open_interest"], smoothing_method, smoothing_period)

    return out


# ─────────────────────────────────────────────────────────────
# COT / WILLCO INDICES
# ─────────────────────────────────────────────────────────────

def compute_indices(
    df: pd.DataFrame,
    method: str,
    primary_lb: int,
    secondary_lb: int,
) -> pd.DataFrame:
    """
    Compute primary and secondary index for all three groups.

    method = 'LW_Index'  → columns: comm_idx_p/s, lrg_idx_p/s, sml_idx_p/s
    method = 'Percentile'→ same column names, Percentile values
    method = 'Both'      → base columns (LW_Index) + *_lw and *_pct variants.
                           Base comm_idx_p etc. always = LW_Index for signal compat.
    """
    out = df.copy()
    oi  = out["oi_smooth"]

    if method == "WillCo":
        for suffix, lb in (("p", primary_lb), ("s", secondary_lb)):
            for grp in ("comm", "lrg", "sml"):
                net = out[f"{grp}_net"]
                lw_vals  = compute_index(net, oi, "LW_Index",  lb)
                pct_vals = compute_index(net, oi, "Percentile", lb)
                # Base columns = LW_Index (signals always use these)
                out[f"{grp}_idx_{suffix}"]     = lw_vals
                # Named variants for dual-method charting
                out[f"{grp}_idx_{suffix}_lw"]  = lw_vals
                out[f"{grp}_idx_{suffix}_pct"] = pct_vals
    else:
        for suffix, lb in (("p", primary_lb), ("s", secondary_lb)):
            out[f"comm_idx_{suffix}"] = compute_index(out["comm_net"], oi, method, lb)
            out[f"lrg_idx_{suffix}"]  = compute_index(out["lrg_net"],  oi, method, lb)
            out[f"sml_idx_{suffix}"]  = compute_index(out["sml_net"],  oi, method, lb)

    return out


# ─────────────────────────────────────────────────────────────
# PCT_LONG  (no lookback — pure position split)
# ─────────────────────────────────────────────────────────────

def compute_pct_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pct_Long = long / (long + short) × 100  per group.
    No lookback, no parameters — purely arithmetic on raw CFTC positions.
    Always 0–100%.  50% = perfectly neutral.
    """
    out = df.copy()
    for grp in ("comm", "lrg", "sml"):
        longs  = out[f"{grp}_long"]
        shorts = out[f"{grp}_short"]
        total  = (longs + shorts).replace(0, np.nan)
        out[f"{grp}_pct_long"] = (longs / total * 100).fillna(50.0)
    return out


# ─────────────────────────────────────────────────────────────
# TREND ANALYSIS
# ─────────────────────────────────────────────────────────────

def compute_trend(df: pd.DataFrame, cum_change_periods: list[str]) -> pd.DataFrame:
    """
    Add trend metrics to the DataFrame.
    cum_change_periods: e.g. ['4W','13W','26W']
    """
    out = df.copy()

    # Cumulative net change over N weeks
    period_weeks = {"4W": 4, "13W": 13, "26W": 26}
    for label in cum_change_periods:
        weeks = period_weeks.get(label, 4)
        out[f"comm_cum_{label}"] = out["comm_net"].diff(weeks)

    # Rate of Change %
    out["comm_roc_4w"]  = out["comm_net"].pct_change(4)  * 100
    out["comm_roc_13w"] = out["comm_net"].pct_change(13) * 100

    # vs 13-week MA
    out["comm_ma13"]    = out["comm_net"].rolling(13).mean()
    out["comm_vs_ma"]   = out["comm_net"] - out["comm_ma13"]

    return out


# ─────────────────────────────────────────────────────────────
# OPEN INTEREST ANALYSIS
# ─────────────────────────────────────────────────────────────

def compute_oi_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Identify who is driving OI changes each week."""
    out = df.copy()

    comm_net_chg = out["comm_long_chg"].fillna(0) - out["comm_short_chg"].fillna(0)
    lrg_net_chg  = out["lrg_long_chg"].fillna(0)  - out["lrg_short_chg"].fillna(0)
    sml_net_chg  = out["sml_long_chg"].fillna(0)  - out["sml_short_chg"].fillna(0)

    out["comm_net_chg"] = comm_net_chg
    out["lrg_net_chg"]  = lrg_net_chg
    out["sml_net_chg"]  = sml_net_chg

    # Who drove the largest absolute OI change this week
    abs_changes = pd.DataFrame({
        "comm": comm_net_chg.abs(),
        "lrg":  lrg_net_chg.abs(),
        "sml":  sml_net_chg.abs(),
    })
    out["oi_driver"] = abs_changes.idxmax(axis=1)   # 'comm' | 'lrg' | 'sml'

    return out


# ─────────────────────────────────────────────────────────────
# MARKET MAKER SPREADING
# ─────────────────────────────────────────────────────────────

def compute_spreading(df: pd.DataFrame) -> pd.DataFrame:
    """Compute spreading % of OI and its 13-week percentile."""
    out = df.copy()
    out["spreading_pct"] = (
        out["lrg_spread"].div(out["open_interest"].replace(0, np.nan)) * 100
    ).fillna(0.0)
    out["spreading_ma13"] = out["spreading_pct"].rolling(13).mean()
    out["spreading_vs_ma"] = out["spreading_pct"] - out["spreading_ma13"]
    return out


# ─────────────────────────────────────────────────────────────
# HISTORICAL PERCENTILE RANKS
# ─────────────────────────────────────────────────────────────

def compute_historical_ranks(
    df: pd.DataFrame,
    periods: list[str],
    method: str,
    primary_lb: int,
) -> dict[str, dict[str, float]]:
    """
    Return {period_label: {group: percentile_rank_%}}.
    Uses the primary index column for ranking.
    """
    results: dict[str, dict[str, float]] = {}

    for label in periods:
        weeks = period_label_to_weeks(label)
        n_rows = weeks if weeks > 0 else len(df)

        results[label] = {
            "comm": percentile_rank(df["comm_idx_p"], n_rows),
            "lrg":  percentile_rank(df["lrg_idx_p"],  n_rows),
            "sml":  percentile_rank(df["sml_idx_p"],  n_rows),
            "oi":   percentile_rank(df["open_interest"], n_rows),
        }

    return results


# ─────────────────────────────────────────────────────────────
# SNAPSHOT — latest bar values
# ─────────────────────────────────────────────────────────────

def latest_snapshot(df: pd.DataFrame) -> dict:
    """
    Extract all relevant values from the most recent weekly bar.
    Returns a flat dict used by signals.py and display layers.
    """
    if df.empty:
        return {}

    row  = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row

    def _val(col: str, default=float("nan")):
        return row[col] if col in df.columns else default

    def _delta(col: str):
        return _val(col) - (prev[col] if col in df.columns else 0)

    snap = {
        # Date
        "date":            str(_val("date"))[:10],
        # Open Interest
        "open_interest":   _val("open_interest"),
        "oi_chg":          _val("oi_chg"),
        "oi_driver":       _val("oi_driver", "—"),
        "conc_top4_long":  _val("conc_top4_long"),
        "conc_top4_short": _val("conc_top4_short"),
        "conc_top8_long":  _val("conc_top8_long"),
        "conc_top8_short": _val("conc_top8_short"),
        # Net positions
        "comm_net":   _val("comm_net"),   "comm_long":   _val("comm_long"),   "comm_short":   _val("comm_short"),
        "lrg_net":    _val("lrg_net"),    "lrg_long":    _val("lrg_long"),    "lrg_short":    _val("lrg_short"),
        "sml_net":    _val("sml_net"),    "sml_long":    _val("sml_long"),    "sml_short":    _val("sml_short"),
        # Week-over-week deltas
        "comm_net_delta": _val("comm_net_chg"),
        "lrg_net_delta":  _val("lrg_net_chg"),
        "sml_net_delta":  _val("sml_net_chg"),
        # WillCo raw % of OI
        "comm_willco_raw": (
            (_val("comm_net") / _val("open_interest")) * 100
            if _val("open_interest") != 0 else float("nan")
        ),
        "lrg_willco_raw":  (
            (_val("lrg_net") / _val("open_interest")) * 100
            if _val("open_interest") != 0 else float("nan")
        ),
        "sml_willco_raw":  (
            (_val("sml_net") / _val("open_interest")) * 100
            if _val("open_interest") != 0 else float("nan")
        ),
        # Primary index
        "comm_idx_p": _val("comm_idx_p"),
        "lrg_idx_p":  _val("lrg_idx_p"),
        "sml_idx_p":  _val("sml_idx_p"),
        # Secondary index
        "comm_idx_s": _val("comm_idx_s"),
        "lrg_idx_s":  _val("lrg_idx_s"),
        "sml_idx_s":  _val("sml_idx_s"),
        # Trend
        "comm_vs_ma":   _val("comm_vs_ma"),
        "comm_roc_4w":  _val("comm_roc_4w"),
        "comm_roc_13w": _val("comm_roc_13w"),
        # Spreading
        "spreading_pct":    _val("spreading_pct"),
        "spreading_vs_ma":  _val("spreading_vs_ma"),
    }

    # Cumulative changes
    for col in df.columns:
        if col.startswith("comm_cum_"):
            snap[col] = _val(col)

    # Both-method variant values (populated when analysis_method = Both)
    for grp in ("comm", "lrg", "sml"):
        for suffix in ("p", "s"):
            for variant in ("lw", "pct"):
                col = f"{grp}_idx_{suffix}_{variant}"
                if col in df.columns:
                    snap[col] = _val(col)

    # Pct_Long columns
    for col in ("comm_pct_long", "lrg_pct_long", "sml_pct_long"):
        if col in df.columns:
            snap[col] = _val(col)

    # Proximity columns (populated by proximity.compute_proximity)
    for col in ("prox_comm", "prox_lrg", "prox_sml"):
        if col in df.columns:
            snap[col] = _val(col)

    return snap


# ─────────────────────────────────────────────────────────────
# ORCHESTRATION
# ─────────────────────────────────────────────────────────────

def run_calculations(
    df: pd.DataFrame,
    cfg: AppConfig,
    instrument: InstrumentConfig,
) -> tuple[pd.DataFrame, dict]:
    """
    Full calculation pipeline for one instrument.

    Returns
    -------
    enriched_df  : full time-series with all computed columns
    snapshot     : flat dict of latest-bar values
    """
    primary_lb, secondary_lb = resolve_lookback(cfg, instrument)

    df = compute_net_positions(df, cfg.smoothing_method, cfg.smoothing_period)
    df = compute_indices(df, cfg.analysis_method, primary_lb, secondary_lb)
    df = compute_pct_long(df)
    df = compute_trend(df, cfg.cum_change_periods)
    df = compute_oi_analysis(df)
    df = compute_spreading(df)

    snap = latest_snapshot(df)
    snap["primary_lookback"]   = primary_lb
    snap["secondary_lookback"] = secondary_lb

    return df, snap
