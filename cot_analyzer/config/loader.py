"""
loader.py
Reads user_input/user_config.csv and user_input/instruments.csv,
validates values, and returns typed dataclasses consumed by the rest
of the application.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────
# DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class InstrumentConfig:
    name: str
    cftc_code: str
    asset_class: str
    lookback_override: int | None      # None → use global / auto
    report_type_override: str | None   # None → use global report_type
    ticker: str                        # yfinance ticker for Proximity chart ('' = not available)
    description: str
    notes: str


@dataclass
class AppConfig:
    # Group 1 — Data
    report_type: str                   # Legacy | Disaggregated | Financial
    include_options: bool
    data_years_history: int
    cache_enabled: bool
    auto_refresh: bool
    hist_data_before_2003: bool        # True → download pre-2003 CFTC archive

    # Group 2 — Analysis
    analysis_method: str               # LW_Index | Percentile | Both
    lookback_mode: str                 # Auto | Manual
    primary_lookback_weeks: int
    secondary_lookback_weeks: int
    show_secondary_lookback: bool
    smoothing_method: str              # None | SMA | EMA | WMA | RMA
    smoothing_period: int

    # Group 3 — Signals
    heavy_buyers_level: int
    heavy_sellers_level: int
    confluence_enabled: bool
    trend_weighting_enabled: bool
    trend_ma_period: int

    # Group 4 — Historical
    show_historical_table: bool
    historical_periods: list[str]      # e.g. ['1M','3M','6M','1Y','3Y','All']
    trading_days_mode: str             # Weekdays | 24_7

    # Group 5 — OI Analysis
    show_oi_analysis: bool
    show_concentration: bool

    # Group 6 — Market State
    show_market_state: bool
    show_best_setup: bool
    show_trading_tips: bool

    # Group 7 — Trend
    show_trend_analysis: bool
    cum_change_periods: list[str]

    # Group 8 — Market Maker
    show_market_maker: bool

    # Group 9 — Output
    output_mode: str                   # terminal | csv | both
    output_folder: Path
    display_mode: str                  # Full | Compact
    color_theme: str                   # Dark | Light
    show_chart: bool
    chart_type: str                    # COT_Report | COT_Index | COT_Proximity | Figure_A | All
    chart_format: str                  # png | html | svg | both
    proximity_lookback_weeks: int
    price_source: str                  # yfinance
    generate_pdf_report: bool
    generate_txt_report: bool = False
    txt_report_format: str = "txt"

    # Group 9 — chart display range (None = full range)
    chart_display_range: tuple | None = None   # (datetime, datetime) or None
    chart_display_ticks: str = "auto"          # auto | weekly | monthly | yearly
    research_tag: str = ""                     # Custom suffix for output folder

    # Instruments (populated by load_instruments)
    instruments: list[InstrumentConfig] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# TYPE COERCION
# ─────────────────────────────────────────────────────────────

def _coerce(value: str, dtype: str) -> Any:
    """Convert a raw CSV string to the correct Python type."""
    value = value.strip()
    if dtype == "bool":
        return value.lower() in ("true", "1", "yes")
    if dtype == "int":
        return int(value)
    if dtype == "float":
        return float(value)
    if dtype == "list":
        return [v.strip() for v in value.split("|") if v.strip()]
    # string (default)
    return value


def normalize_name(name: str) -> str:
    """Normalize instrument names for robust matching (ignore case, dashes, extra spaces)."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", name.lower())
    return " ".join(cleaned.split())


# ─────────────────────────────────────────────────────────────
# CSV READERS
# ─────────────────────────────────────────────────────────────

def _read_config_csv(path: Path) -> dict[str, Any]:
    """
    Parse user_config.csv.
    Skips comment rows (group, parameter starting with '#').
    Returns {parameter: coerced_value}.
    """
    params: dict[str, Any] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            param = row.get("parameter", "").strip()
            if not param or param.startswith("#"):
                continue
            raw_value = row.get("value", "").strip()
            dtype     = row.get("type", "string").strip()
            params[param] = _coerce(raw_value, dtype)
    return params


def _read_instruments_csv(path: Path) -> list[InstrumentConfig]:
    """
    Parse instruments.csv.
    Returns list of (InstrumentConfig, enabled_flag).
    """
    instruments: list[tuple[InstrumentConfig, bool]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = row.get("name", "").strip()
            if not name or name.startswith("#"):
                continue
            enabled = row.get("enabled", "False").strip().lower() in ("true", "1", "yes")

            raw_lookback = row.get("lookback_override", "").strip()
            raw_report   = row.get("report_type_override", "").strip()

            instruments.append((InstrumentConfig(
                name                = name,
                cftc_code           = row.get("cftc_code", "").strip(),
                asset_class         = row.get("asset_class", "").strip(),
                lookback_override   = int(raw_lookback) if raw_lookback else None,
                report_type_override= raw_report if raw_report else None,
                ticker              = row.get("ticker", "").strip(),
                description         = row.get("description", "").strip(),
                notes               = row.get("notes", "").strip(),
            ), enabled))
    return instruments


# ─────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────

def load_config(
    project_root: Path,
    instrument_name_override: str | None = None,
    range_override: str | None = None,
    tag_override: str | None = None,
) -> AppConfig:
    """
    Load and validate both CSVs.  Returns a fully populated AppConfig.

    Overrides (passed via CLI in main.py):
      instrument_name_override: only process this instrument (if found)
      range_override          : format "DD-MM-YYYY:DD-MM-YYYY"
      tag_override            : custom research tag
    """
    config_path      = project_root / "user_input" / "user_config.csv"
    instruments_path = project_root / "user_input" / "instruments.csv"

    for p in (config_path, instruments_path):
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")

    p = _read_config_csv(config_path)

    # ── Apply Overrides ──────────────────────────────────────
    if range_override:
        p["chart_display_range"] = range_override
    if tag_override:
        p["research_tag"] = tag_override

    _validate(p)

    # Parse chart_display_range: "DD-MM-YYYY:DD-MM-YYYY" or empty
    chart_display_range = None
    raw_cdr = p.get("chart_display_range", "").strip()
    if raw_cdr:
        parts = raw_cdr.split(":")
        if len(parts) != 2:
            raise ValueError(
                f"chart_display_range must be 'DD-MM-YYYY:DD-MM-YYYY', got: {raw_cdr!r}"
            )
        try:
            cdr_start = datetime.strptime(parts[0].strip(), "%d-%m-%Y")
            cdr_end   = datetime.strptime(parts[1].strip(), "%d-%m-%Y")
        except ValueError:
            raise ValueError(
                f"chart_display_range dates must use DD-MM-YYYY format, got: {raw_cdr!r}"
            )
        if cdr_start >= cdr_end:
            raise ValueError(
                f"chart_display_range start must be before end: {raw_cdr!r}"
            )
        chart_display_range = (cdr_start, cdr_end)

    cfg = AppConfig(
        # Group 1
        report_type           = p["report_type"],
        include_options       = p["include_options"],
        data_years_history    = p["data_years_history"],
        cache_enabled         = p["cache_enabled"],
        auto_refresh          = p["auto_refresh"],
        hist_data_before_2003 = p.get("hist_data_before_2003", False),
        # Group 2
        analysis_method       = p["analysis_method"],
        lookback_mode         = p["lookback_mode"],
        primary_lookback_weeks   = p["primary_lookback_weeks"],
        secondary_lookback_weeks = p["secondary_lookback_weeks"],
        show_secondary_lookback  = p["show_secondary_lookback"],
        smoothing_method      = p["smoothing_method"],
        smoothing_period      = p["smoothing_period"],
        # Group 3
        heavy_buyers_level    = p["heavy_buyers_level"],
        heavy_sellers_level   = p["heavy_sellers_level"],
        confluence_enabled    = p["confluence_enabled"],
        trend_weighting_enabled = p["trend_weighting_enabled"],
        trend_ma_period       = p["trend_ma_period"],
        # Group 4
        show_historical_table = p["show_historical_table"],
        historical_periods    = p["historical_periods"],
        trading_days_mode     = p["trading_days_mode"],
        # Group 5
        show_oi_analysis      = p["show_oi_analysis"],
        show_concentration    = p["show_concentration"],
        # Group 6
        show_market_state     = p["show_market_state"],
        show_best_setup       = p["show_best_setup"],
        show_trading_tips     = p["show_trading_tips"],
        # Group 7
        show_trend_analysis   = p["show_trend_analysis"],
        cum_change_periods    = p["cum_change_periods"],
        # Group 8
        show_market_maker     = p["show_market_maker"],
        # Group 9
        output_mode           = p["output_mode"],
        output_folder         = project_root / p["output_folder"],
        display_mode          = p["display_mode"],
        color_theme           = p["color_theme"],
        show_chart                = p["show_chart"],
        chart_type                = p.get("chart_type", "COT_Index"),
        chart_format              = p.get("chart_format", "html"),
        proximity_lookback_weeks  = p.get("proximity_lookback_weeks", 13),
        price_source              = p.get("price_source", "yfinance"),
        generate_pdf_report       = p.get("generate_pdf_report", False),
        generate_txt_report       = p.get("generate_txt_report", False),
        txt_report_format         = p.get("txt_report_format", "txt"),
        chart_display_range       = chart_display_range,
        chart_display_ticks       = p.get("chart_display_ticks", "auto").lower(),
        research_tag              = p.get("research_tag", "").strip(),
    )

    # Apply output folder suffix to prevent overwriting
    # Pattern: charts/research/[tag]_[range]
    if cfg.research_tag or cfg.chart_display_range:
        range_part = "FullRange"
        if cfg.chart_display_range:
            s, e = cfg.chart_display_range
            range_part = f"{s.strftime('%Y%m%d')}-{e.strftime('%Y%m%d')}"
        
        tag_part = "".join(c for c in cfg.research_tag if c.isalnum() or c in "-_")
        
        if tag_part:
            folder_name = f"{tag_part}_{range_part}"
        else:
            folder_name = range_part
            
        cfg.output_folder = cfg.output_folder / "charts" / "research" / folder_name

    all_instruments = _read_instruments_csv(instruments_path)

    # ── Instrument Filtering ─────────────────────────────────
    if instrument_name_override:
        # Override case: process strictly this instrument, even if disabled in CSV
        target = normalize_name(instrument_name_override)
        found = [
            i for i, _ in all_instruments 
            if normalize_name(i.name) == target
        ]
        if not found:
            raise ValueError(f"Instrument '{instrument_name_override}' not found in instruments.csv")
        cfg.instruments = found
    else:
        # Standard case: only use instruments marked as enabled=True in CSV
        cfg.instruments = [i for i, enabled in all_instruments if enabled]

    if not cfg.instruments:
        raise ValueError(
            "No instruments are enabled in instruments.csv. "
            "Set at least one row to enabled=True."
        )

    return cfg


def _validate(p: dict[str, Any]) -> None:
    """Raise ValueError for out-of-range or invalid values."""
    checks = [
        ("report_type",      ["Legacy", "Disaggregated", "Financial"]),
        ("analysis_method",  ["LW_Index", "Percentile", "WillCo"]),
        ("lookback_mode",    ["Auto", "Manual"]),
        ("smoothing_method", ["None", "SMA", "EMA", "WMA", "RMA"]),
        ("output_mode",      ["terminal", "csv", "both"]),
        ("display_mode",     ["Full", "Compact"]),
        ("color_theme",      ["Dark", "Light"]),
        ("chart_type",       ["COT_Report", "COT_Index", "COT_Proximity", "Figure_A", "Figure_B", "Figure_B_Groups", "Figure_C", "Figure_D", "Figure_E", "Figure_F", "All"]),
        ("chart_format",     ["png", "html", "svg", "both"]),
        ("trading_days_mode",["Weekdays", "24_7"]),
        ("chart_display_ticks", ["auto", "weekly", "monthly", "yearly"]),
    ]
    for key, valid in checks:
        if p.get(key) not in valid:
            raise ValueError(
                f"Invalid value for '{key}': {p.get(key)!r}. "
                f"Valid options: {valid}"
            )

    if p.get("txt_report_format", "txt") not in ("txt", "html", "both"):
        raise ValueError("txt_report_format must be txt, html, or both")

    if p["heavy_sellers_level"] >= p["heavy_buyers_level"]:
        raise ValueError(
            f"heavy_sellers_level ({p['heavy_sellers_level']}) must be "
            f"less than heavy_buyers_level ({p['heavy_buyers_level']})"
        )
