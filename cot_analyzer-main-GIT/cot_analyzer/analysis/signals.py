"""
signals.py
Signal generation layer: Market State scoring, confluence detection,
best-setup identification, and trading tips text.
All functions are pure (no I/O); they operate on a snapshot dict.
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────
# MARKET STATE
# ─────────────────────────────────────────────────────────────

def market_state(
    comm_idx: float,
    lrg_idx: float,
    heavy_buyers: int,
    heavy_sellers: int,
) -> str:
    """
    Classify the current market state from Commercial + Large Spec indices.

    Returns one of:
        STRONG BULLISH | BULLISH | NEUTRAL BULLISH
        STRONG BEARISH | BEARISH | NEUTRAL BEARISH
        NEUTRAL
    """
    comm_bull = comm_idx >= heavy_buyers
    comm_bear = comm_idx <= heavy_sellers
    lrg_bull  = lrg_idx  >= heavy_buyers
    lrg_bear  = lrg_idx  <= heavy_sellers

    # Confluence: both groups aligned (highest conviction)
    if comm_bull and lrg_bear:
        return "STRONG BULLISH"
    if comm_bear and lrg_bull:
        return "STRONG BEARISH"

    # Single group extreme
    mid = (heavy_buyers + heavy_sellers) / 2.0
    if comm_bull:
        return "BULLISH" if comm_idx < (heavy_buyers + 100) / 2 else "BULLISH"
    if comm_bear:
        return "BEARISH"

    # Lean — not yet extreme but directionally biased
    if comm_idx > mid:
        return "NEUTRAL BULLISH"
    if comm_idx < mid:
        return "NEUTRAL BEARISH"
    return "NEUTRAL"


# ─────────────────────────────────────────────────────────────
# CONFLUENCE DETECTION
# ─────────────────────────────────────────────────────────────

def confluence_signal(
    comm_idx: float,
    lrg_idx: float,
    heavy_buyers: int,
    heavy_sellers: int,
    enabled: bool,
) -> str:
    """
    Return 'BULL' | 'BEAR' | '' depending on whether the classic
    LW confluence setup is active.

    Bull confluence: Commercial ≥ heavy_buyers AND Large Spec ≤ heavy_sellers.
    Bear confluence: Commercial ≤ heavy_sellers AND Large Spec ≥ heavy_buyers.
    """
    if not enabled:
        return ""
    if comm_idx >= heavy_buyers and lrg_idx <= heavy_sellers:
        return "BULL"
    if comm_idx <= heavy_sellers and lrg_idx >= heavy_buyers:
        return "BEAR"
    return ""


# ─────────────────────────────────────────────────────────────
# TREND WEIGHT ADJUSTMENT
# ─────────────────────────────────────────────────────────────

def trend_adjusted_score(
    comm_idx: float,
    comm_vs_ma: float,
    trend_weighting_enabled: bool,
) -> float:
    """
    Optionally boost / penalise the base comm_idx score by trend direction.
    When comm_net is above its 13w MA → trend confirmed → slight boost.
    Returns an adjusted score (not clamped; display layer handles it).
    """
    if not trend_weighting_enabled:
        return comm_idx
    boost = 5.0 if comm_vs_ma > 0 else -5.0
    return comm_idx + boost


# ─────────────────────────────────────────────────────────────
# BEST SETUP DETECTION
# ─────────────────────────────────────────────────────────────

def best_setup(snap: dict, cfg_heavy_buyers: int, cfg_heavy_sellers: int) -> str:
    """
    Identify the highest-probability trade setup visible in the snapshot.
    Returns a short label string or '' if no qualifying setup found.

    Priority order:
      1. LW Confluence (comm extreme + large spec opposite)
      2. Secondary-lookback confirmation (both lookbacks aligned)
      3. Commercial extreme alone
    """
    comm_p = snap.get("comm_idx_p", 50.0)
    lrg_p  = snap.get("lrg_idx_p",  50.0)
    comm_s = snap.get("comm_idx_s", 50.0)

    # 1. Confluence
    cf = confluence_signal(comm_p, lrg_p, cfg_heavy_buyers, cfg_heavy_sellers, True)
    if cf == "BULL":
        return "LW BULL CONFLUENCE"
    if cf == "BEAR":
        return "LW BEAR CONFLUENCE"

    # 2. Dual-lookback agreement
    comm_bull_p = comm_p >= cfg_heavy_buyers
    comm_bear_p = comm_p <= cfg_heavy_sellers
    comm_bull_s = comm_s >= cfg_heavy_buyers
    comm_bear_s = comm_s <= cfg_heavy_sellers

    if comm_bull_p and comm_bull_s:
        return "DUAL-LB BULL SIGNAL"
    if comm_bear_p and comm_bear_s:
        return "DUAL-LB BEAR SIGNAL"

    # 3. Single extreme
    if comm_bull_p:
        return "COMM BULL EXTREME"
    if comm_bear_p:
        return "COMM BEAR EXTREME"

    return ""


# ─────────────────────────────────────────────────────────────
# TRADING TIPS TEXT
# ─────────────────────────────────────────────────────────────

def trading_tips(
    state: str,
    setup: str,
    confluence: str,
    snap: dict,
    heavy_buyers: int,
    heavy_sellers: int,
) -> list[str]:
    """
    Generate 2-4 plain-language trading tips based on the current signals.
    Returns a list of strings for display.
    """
    tips: list[str] = []

    comm_p = snap.get("comm_idx_p", 50.0)
    lrg_p  = snap.get("lrg_idx_p",  50.0)
    sml_p  = snap.get("sml_idx_p",  50.0)
    comm_vs_ma = snap.get("comm_vs_ma", 0.0)

    # Tip 1 — market state context
    if "STRONG BULLISH" in state:
        tips.append("Commercials AND Large Specs aligned — highest-conviction bull setup.")
    elif "STRONG BEARISH" in state:
        tips.append("Commercials AND Large Specs aligned — highest-conviction bear setup.")
    elif "BULLISH" in state:
        tips.append("Commercials are at extreme long — watch for price reversal higher.")
    elif "BEARISH" in state:
        tips.append("Commercials are at extreme short — watch for price reversal lower.")
    elif state == "NEUTRAL":
        tips.append("No extreme positioning — wait for clearer COT signal before acting.")

    # Tip 2 — retail (small spec) contrarian
    mid = (heavy_buyers + heavy_sellers) / 2.0
    if sml_p >= heavy_buyers:
        tips.append(f"Small Specs are crowded LONG ({sml_p:.0f}%) — contrarian caution for bulls.")
    elif sml_p <= heavy_sellers:
        tips.append(f"Small Specs are crowded SHORT ({sml_p:.0f}%) — contrarian support for bulls.")

    # Tip 3 — trend confirmation
    if comm_vs_ma > 0 and comm_p >= mid:
        tips.append("Commercial net is above 13w MA — trend confirms bullish bias.")
    elif comm_vs_ma < 0 and comm_p < mid:
        tips.append("Commercial net is below 13w MA — trend confirms bearish bias.")

    # Tip 4 — reminder about COT lag
    tips.append("COT data is released weekly with a 3-day lag — use with price action.")

    return tips[:4]


# ─────────────────────────────────────────────────────────────
# ORCHESTRATION
# ─────────────────────────────────────────────────────────────

def run_signals(snap: dict, cfg) -> dict:
    """
    Compute all signal outputs for one instrument snapshot.

    Parameters
    ----------
    snap : dict from calculator.latest_snapshot()
    cfg  : AppConfig

    Returns
    -------
    signals dict with keys:
        market_state, confluence, setup, tips, trend_score
    """
    comm_p = snap.get("comm_idx_p", 50.0)
    lrg_p  = snap.get("lrg_idx_p",  50.0)
    comm_vs_ma = snap.get("comm_vs_ma", 0.0)

    hb = cfg.heavy_buyers_level
    hs = cfg.heavy_sellers_level

    state     = market_state(comm_p, lrg_p, hb, hs)
    cf        = confluence_signal(comm_p, lrg_p, hb, hs, cfg.confluence_enabled)
    setup     = best_setup(snap, hb, hs) if cfg.show_best_setup else ""
    t_score   = trend_adjusted_score(comm_p, comm_vs_ma, cfg.trend_weighting_enabled)
    tips_list = trading_tips(state, setup, cf, snap, hb, hs) if cfg.show_trading_tips else []

    return {
        "market_state": state,
        "confluence":   cf,
        "setup":        setup,
        "tips":         tips_list,
        "trend_score":  round(t_score, 1),
    }
