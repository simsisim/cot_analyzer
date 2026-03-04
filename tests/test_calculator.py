"""
test_calculator.py
Unit tests for the core calculation functions.
Run with: pytest tests/
"""

import numpy as np
import pandas as pd
import pytest

from cot_analyzer.utils.helpers import (
    smooth,
    willco_index,
    lw_index,
    percentile_index,
    percentile_rank,
    format_contracts,
    format_pct,
    cache_is_stale,
    period_label_to_weeks,
)
from cot_analyzer.analysis.calculator import (
    compute_net_positions,
    compute_indices,
    compute_trend,
    compute_oi_analysis,
    latest_snapshot,
)
from cot_analyzer.analysis.signals import (
    market_state,
    confluence_signal,
    best_setup,
)


# ─────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    """Minimal weekly COT DataFrame with 60 rows."""
    n = 60
    dates = pd.date_range("2022-01-07", periods=n, freq="W-FRI")
    rng = np.random.default_rng(42)
    oi = 500_000 + rng.integers(-50_000, 50_000, n).cumsum().clip(100_000, 900_000)
    df = pd.DataFrame({
        "date":          dates,
        "market_name":   "TEST",
        "cftc_code":     "000000",
        "open_interest": oi.astype(float),
        "comm_long":     rng.integers(100_000, 300_000, n).astype(float),
        "comm_short":    rng.integers(100_000, 300_000, n).astype(float),
        "lrg_long":      rng.integers( 80_000, 200_000, n).astype(float),
        "lrg_short":     rng.integers( 80_000, 200_000, n).astype(float),
        "lrg_spread":    rng.integers(  5_000,  20_000, n).astype(float),
        "sml_long":      rng.integers( 20_000,  80_000, n).astype(float),
        "sml_short":     rng.integers( 20_000,  80_000, n).astype(float),
        "oi_chg":        rng.integers(-10_000,  10_000, n).astype(float),
        "comm_long_chg": rng.integers( -5_000,   5_000, n).astype(float),
        "comm_short_chg":rng.integers( -5_000,   5_000, n).astype(float),
        "lrg_long_chg":  rng.integers( -5_000,   5_000, n).astype(float),
        "lrg_short_chg": rng.integers( -5_000,   5_000, n).astype(float),
        "sml_long_chg":  rng.integers( -2_000,   2_000, n).astype(float),
        "sml_short_chg": rng.integers( -2_000,   2_000, n).astype(float),
        "pct_comm_long": rng.uniform(30, 70, n),
        "conc_top4_long":  rng.uniform(20, 50, n),
        "conc_top4_short": rng.uniform(20, 50, n),
        "conc_top8_long":  rng.uniform(30, 60, n),
        "conc_top8_short": rng.uniform(30, 60, n),
    })
    return df


# ─────────────────────────────────────────────────────────────
# SMOOTHING
# ─────────────────────────────────────────────────────────────

def test_smooth_none(sample_df):
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = smooth(s, "None", 3)
    pd.testing.assert_series_equal(result, s)


def test_smooth_sma():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = smooth(s, "SMA", 3)
    assert result.iloc[-1] == pytest.approx(4.0)


def test_smooth_ema():
    s = pd.Series([1.0, 1.0, 1.0, 1.0, 5.0])
    result = smooth(s, "EMA", 3)
    assert result.iloc[-1] > 1.0  # EMA responds to the spike

def test_smooth_invalid():
    with pytest.raises(ValueError, match="Unknown smoothing method"):
        smooth(pd.Series([1.0, 2.0]), "BOGUS", 3)


# ─────────────────────────────────────────────────────────────
# INDEX FUNCTIONS
# ─────────────────────────────────────────────────────────────

def test_willco_range():
    n = 40
    net = pd.Series(np.linspace(-100_000, 100_000, n))
    oi  = pd.Series([500_000.0] * n)
    result = willco_index(net, oi, 26)
    # After lookback is warm, should be in [0, 100]
    warm = result.dropna()
    assert (warm >= 0).all() and (warm <= 100).all()


def test_lw_index_range():
    net = pd.Series(np.linspace(-100_000, 100_000, 40))
    result = lw_index(net, 26)
    warm = result.iloc[26:]
    assert (warm >= 0).all() and (warm <= 100).all()


def test_percentile_index_can_exceed():
    """Percentile index should allow values slightly outside 0-100."""
    net = pd.Series(np.linspace(-100_000, 200_000, 60))
    result = percentile_index(net, 26)
    # At least the final value should be > 100 (new high)
    assert result.iloc[-1] > 100.0


# ─────────────────────────────────────────────────────────────
# CALCULATOR — NET POSITIONS
# ─────────────────────────────────────────────────────────────

def test_compute_net_positions_columns(sample_df):
    out = compute_net_positions(sample_df, "None", 1)
    for col in ("comm_net", "lrg_net", "sml_net", "comm_net_raw", "lrg_net_raw", "sml_net_raw", "oi_smooth"):
        assert col in out.columns, f"Missing column: {col}"


def test_net_position_arithmetic(sample_df):
    out = compute_net_positions(sample_df, "None", 1)
    expected = sample_df["comm_long"] - sample_df["comm_short"]
    pd.testing.assert_series_equal(out["comm_net_raw"], expected, check_names=False)


# ─────────────────────────────────────────────────────────────
# CALCULATOR — INDICES
# ─────────────────────────────────────────────────────────────

def test_compute_indices_columns(sample_df):
    df = compute_net_positions(sample_df, "None", 1)
    df = compute_indices(df, "WillCo", 26, 52)
    for suffix in ("p", "s"):
        for grp in ("comm", "lrg", "sml"):
            assert f"{grp}_idx_{suffix}" in df.columns


# ─────────────────────────────────────────────────────────────
# CALCULATOR — TREND
# ─────────────────────────────────────────────────────────────

def test_compute_trend_columns(sample_df):
    df = compute_net_positions(sample_df, "None", 1)
    df = compute_trend(df, ["4W", "13W"])
    assert "comm_cum_4W"  in df.columns
    assert "comm_cum_13W" in df.columns
    assert "comm_roc_4w"  in df.columns
    assert "comm_ma13"    in df.columns


# ─────────────────────────────────────────────────────────────
# CALCULATOR — OI ANALYSIS
# ─────────────────────────────────────────────────────────────

def test_compute_oi_driver(sample_df):
    df = compute_net_positions(sample_df, "None", 1)
    df = compute_oi_analysis(df)
    assert "oi_driver" in df.columns
    assert df["oi_driver"].isin(["comm", "lrg", "sml"]).all()


# ─────────────────────────────────────────────────────────────
# SNAPSHOT
# ─────────────────────────────────────────────────────────────

def test_latest_snapshot_keys(sample_df):
    df = compute_net_positions(sample_df, "None", 1)
    df = compute_indices(df, "WillCo", 26, 52)
    df = compute_trend(df, ["4W"])
    df = compute_oi_analysis(df)
    snap = latest_snapshot(df)
    assert "comm_idx_p" in snap
    assert "lrg_idx_p"  in snap
    assert "open_interest" in snap


def test_latest_snapshot_empty():
    snap = latest_snapshot(pd.DataFrame())
    assert snap == {}


# ─────────────────────────────────────────────────────────────
# SIGNALS
# ─────────────────────────────────────────────────────────────

def test_market_state_strong_bull():
    state = market_state(comm_idx=92, lrg_idx=8, heavy_buyers=75, heavy_sellers=25)
    assert state == "STRONG BULLISH"


def test_market_state_strong_bear():
    state = market_state(comm_idx=8, lrg_idx=92, heavy_buyers=75, heavy_sellers=25)
    assert state == "STRONG BEARISH"


def test_market_state_neutral():
    state = market_state(comm_idx=50, lrg_idx=50, heavy_buyers=75, heavy_sellers=25)
    assert state == "NEUTRAL"


def test_confluence_bull():
    cf = confluence_signal(92, 5, 75, 25, True)
    assert cf == "BULL"


def test_confluence_bear():
    cf = confluence_signal(5, 92, 75, 25, True)
    assert cf == "BEAR"


def test_confluence_disabled():
    cf = confluence_signal(92, 5, 75, 25, False)
    assert cf == ""


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def test_format_contracts():
    assert format_contracts(1_234_567) == "1.23M"
    assert format_contracts(-5_678)    == "-5.7K"
    assert format_contracts(42)        == "42"
    assert format_contracts(float("nan")) == "—"


def test_format_pct():
    assert format_pct(42.567) == "42.6%"
    assert format_pct(float("nan")) == "—"


def test_period_label_to_weeks():
    assert period_label_to_weeks("1M")  == 4
    assert period_label_to_weeks("1Y")  == 52
    assert period_label_to_weeks("All") == 0

    with pytest.raises(ValueError):
        period_label_to_weeks("2Y")


def test_percentile_rank_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    rank = percentile_rank(s, 5)
    assert rank == 80.0   # 4 values below 5.0 out of 5


def test_percentile_rank_insufficient_data():
    s = pd.Series([1.0])
    assert pd.isna(percentile_rank(s, 5))
