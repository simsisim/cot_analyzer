"""
constants.py
All static mappings: CFTC column names, instrument registry,
asset-class lookback periods, report-type metric names.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# CFTC RAW CSV COLUMN NAMES  (Legacy Futures-Only report)
# ─────────────────────────────────────────────────────────────
LEGACY_COLS = {
    # Legacy Futures-Only report — uses spaces and parentheses in column names
    "date":              "As of Date in Form YYYY-MM-DD",
    "report_date":       "As of Date in Form YYMMDD",
    "market_name":       "Market and Exchange Names",
    "cftc_code":         "CFTC Contract Market Code",
    "commodity_code":    "CFTC Commodity Code",
    "open_interest":     "Open Interest (All)",
    # --- Positions ---
    "comm_long":         "Commercial Positions-Long (All)",
    "comm_short":        "Commercial Positions-Short (All)",
    "lrg_long":          "Noncommercial Positions-Long (All)",
    "lrg_short":         "Noncommercial Positions-Short (All)",
    "lrg_spread":        "Noncommercial Positions-Spreading (All)",
    "sml_long":          "Nonreportable Positions-Long (All)",
    "sml_short":         "Nonreportable Positions-Short (All)",
    # --- Week-over-week changes ---
    "oi_chg":            "Change in Open Interest (All)",
    "comm_long_chg":     "Change in Commercial-Long (All)",
    "comm_short_chg":    "Change in Commercial-Short (All)",
    "lrg_long_chg":      "Change in Noncommercial-Long (All)",
    "lrg_short_chg":     "Change in Noncommercial-Short (All)",
    "sml_long_chg":      "Change in Nonreportable-Long (All)",
    "sml_short_chg":     "Change in Nonreportable-Short (All)",
    # --- % of OI ---
    "pct_comm_long":     "% of OI-Commercial-Long (All)",
    "pct_comm_short":    "% of OI-Commercial-Short (All)",
    "pct_lrg_long":      "% of OI-Noncommercial-Long (All)",
    "pct_lrg_short":     "% of OI-Noncommercial-Short (All)",
    "pct_sml_long":      "% of OI-Nonreportable-Long (All)",
    "pct_sml_short":     "% of OI-Nonreportable-Short (All)",
    # --- Concentration (CFTC column naming is inconsistent — matched exactly) ---
    "conc_top4_long":    "Concentration-Gross LT = 4 TDR-Long (All)",
    "conc_top4_short":   "Concentration-Gross LT =4 TDR-Short (All)",
    "conc_top8_long":    "Concentration-Gross LT =8 TDR-Long (All)",
    "conc_top8_short":   "Concentration-Gross LT =8 TDR-Short (All)",
    # --- Trader counts ---
    "traders_comm_long":  "Traders-Commercial-Long (All)",
    "traders_comm_short": "Traders-Commercial-Short (All)",
    "traders_lrg_long":   "Traders-Noncommercial-Long (All)",
    "traders_lrg_short":  "Traders-Noncommercial-Short (All)",
}

# Disaggregated Futures-Only column overrides
DISAGG_COLS = {
    "comm_long":   "Prod_Merc_Positions_Long_All",
    "comm_short":  "Prod_Merc_Positions_Short_All",
    "lrg_long":    "M_Money_Positions_Long_All",
    "lrg_short":   "M_Money_Positions_Short_All",
    "lrg_spread":  "M_Money_Positions_Spread_All",
    "sml_long":    "NonRept_Positions_Long_All",
    "sml_short":   "NonRept_Positions_Short_All",
}

# Financial (TFF) Futures-Only column overrides
FINANCIAL_COLS = {
    "comm_long":   "Dealer_Positions_Long_All",
    "comm_short":  "Dealer_Positions_Short_All",
    "lrg_long":    "Lev_Money_Positions_Long_All",
    "lrg_short":   "Lev_Money_Positions_Short_All",
    "lrg_spread":  "Lev_Money_Positions_Spread_All",
    "sml_long":    "NonRept_Positions_Long_All",
    "sml_short":   "NonRept_Positions_Short_All",
}

# cot-reports library report-type identifiers
COT_REPORT_TYPE_MAP = {
    "Legacy":         "legacy_fut",
    "Disaggregated":  "disaggregated_fut",
    "Financial":      "traders_in_fin_fut_fut",
}

# ─────────────────────────────────────────────────────────────
# INSTRUMENT REGISTRY
# cftc_code: the commodity code used for matching in raw CSV
# ─────────────────────────────────────────────────────────────
INSTRUMENTS: dict[str, dict] = {
    # Metals
    "GC - Gold":          {"cftc_code": "088691", "asset_class": "Metal"},
    "MGC - Micro Gold":   {"cftc_code": "088695", "asset_class": "Metal"},
    "SI - Silver":        {"cftc_code": "084691", "asset_class": "Metal"},
    "HG - Copper":        {"cftc_code": "085692", "asset_class": "Metal"},
    "PL - Platinum":      {"cftc_code": "076651", "asset_class": "Metal"},
    "PA - Palladium":     {"cftc_code": "075651", "asset_class": "Metal"},
    "ALI - Aluminum":     {"cftc_code": "191651", "asset_class": "Metal"},
    # Energy
    "CL - Crude Oil":     {"cftc_code": "067651", "asset_class": "Energy"},
    "NG - Natural Gas":   {"cftc_code": "023651", "asset_class": "Energy"},
    # Equity Indices
    "NQ - Nasdaq-100":    {"cftc_code": "209742", "asset_class": "Index"},
    "ES - S&P 500":       {"cftc_code": "13874A", "asset_class": "Index"},
    "YM - Dow":           {"cftc_code": "124606", "asset_class": "Index"},
    "RTY - Russell 2000": {"cftc_code": "239742", "asset_class": "Index"},
    # Bonds
    "ZB - T-Bond 30Y":    {"cftc_code": "020601", "asset_class": "Bond"},
    "ZN - T-Note 10Y":    {"cftc_code": "043602", "asset_class": "Bond"},
    # FX
    "6E - Euro":          {"cftc_code": "099741", "asset_class": "FX"},
    "6J - Yen":           {"cftc_code": "097741", "asset_class": "FX"},
    "6B - GBP":           {"cftc_code": "096742", "asset_class": "FX"},
    "6A - AUD":           {"cftc_code": "232741", "asset_class": "FX"},
    # Crypto
    "BTC - Bitcoin":      {"cftc_code": "133741", "asset_class": "Crypto"},
}

# Auto lookback by asset class (LW recommendation)
AUTO_LOOKBACK: dict[str, int] = {
    "Metal":  13,
    "Energy": 13,
    "Index":  13,
    "Bond":   52,
    "FX":     26,
    "Grain":  26,
    "Crypto": 26,
}

# ─────────────────────────────────────────────────────────────
# DISPLAY LABELS
# ─────────────────────────────────────────────────────────────
GROUP_LABELS = {
    "comm":  "Commercial",
    "lrg":   "Large Spec",
    "sml":   "Small Spec",
}

MARKET_STATE_COLORS = {
    "STRONG BULLISH":   "bright_green",
    "MODERATE BULLISH": "green",
    "LEANING BULLISH":  "dark_green",
    "NEUTRAL":          "white",
    "LEANING BEARISH":  "yellow",
    "MODERATE BEARISH": "red",
    "STRONG BEARISH":   "bright_red",
}

ENTRY_COLORS = {
    "LONG":  "bright_green",
    "SHORT": "bright_red",
    "Wait":  "dim white",
}

# Historical period definitions: label → approximate weeks
HISTORICAL_PERIODS: dict[str, int] = {
    "1M":  4,
    "3M":  13,
    "6M":  26,
    "1Y":  52,
    "3Y":  156,
    "All": 0,    # 0 = use entire available history
}
