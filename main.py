"""
main.py
Entry point for the COT Analyzer.

Usage:
    python main.py                   # uses project root as config location
    python main.py --root /path/to   # custom config/output root

Pipeline:
    1. Load config from user_input/user_config.csv + instruments.csv
    2. Fetch COT data from CFTC (or local Parquet cache)
    3. For each enabled instrument:
       a. Filter & parse raw data
       b. Run calculations (net positions, indices, trend, OI)
       c. Compute historical percentile ranks
       d. Generate signals (market state, confluence, best setup)
       e. Display in terminal (Full or Compact)
       f. Export to CSV / HTML chart if requested
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from rich.console import Console

from cot_analyzer.config.loader import load_config, AppConfig, InstrumentConfig
from cot_analyzer.data.fetcher import fetch_cot_data
from cot_analyzer.data.parser import filter_instrument
from cot_analyzer.data.price_fetcher import fetch_price_data
from cot_analyzer.analysis.calculator import run_calculations, compute_historical_ranks
from cot_analyzer.analysis.proximity import compute_proximity
from cot_analyzer.analysis.signals import run_signals
from cot_analyzer.display.tables import display_instrument
from cot_analyzer.display.exporter import export_results

console = Console()


# ─────────────────────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────────────────────

def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        level=level,
        stream=sys.stderr,
    )


# ─────────────────────────────────────────────────────────────
# PER-INSTRUMENT PROCESSING
# ─────────────────────────────────────────────────────────────

def _process_instrument(
    instrument: InstrumentConfig,
    raw_cache: dict,          # {report_type: raw_df}
    cfg: AppConfig,
    project_root: Path,
) -> dict | None:
    """
    Run the full pipeline for one instrument.
    Returns a result dict or None on error.
    """
    report_type = instrument.report_type_override or cfg.report_type

    # Fetch raw data (may hit cache)
    if report_type not in raw_cache:
        cache_dir = project_root / "data" / "cache"
        try:
            raw_cache[report_type] = fetch_cot_data(
                report_type   = report_type,
                years_history = cfg.data_years_history,
                cache_dir     = cache_dir,
                cache_enabled = cfg.cache_enabled,
                auto_refresh  = cfg.auto_refresh,
            )
        except Exception as exc:
            console.print(f"[red]ERROR fetching {report_type}: {exc}[/red]")
            return None

    raw_df = raw_cache[report_type]

    # Parse to single-instrument time-series
    try:
        df = filter_instrument(raw_df, instrument.cftc_code, report_type)
    except ValueError as exc:
        console.print(f"[yellow]SKIP {instrument.name}: {exc}[/yellow]")
        return None

    # Calculations
    try:
        df, snap = run_calculations(df, cfg, instrument)
    except Exception as exc:
        console.print(f"[red]CALC ERROR {instrument.name}: {exc}[/red]")
        return None

    # Price data — needed for Proximity chart and Figure A candlestick
    needs_price = cfg.chart_type in ("COT_Proximity", "Figure_A", "Figure_B", "Figure_B_Groups", "Figure_C", "Figure_D", "Figure_E", "All")
    df_price = pd.DataFrame()
    if needs_price and instrument.ticker:
        cache_dir = project_root / "data" / "cache"
        df_price = fetch_price_data(
            ticker        = instrument.ticker,
            years_history = cfg.data_years_history,
            cache_dir     = cache_dir,
            auto_refresh  = cfg.auto_refresh,
        )

    if cfg.chart_type in ("COT_Proximity", "All") and not df_price.empty:
        df = compute_proximity(df, df_price, cfg.proximity_lookback_weeks)
        # Refresh snapshot with proximity columns
        from cot_analyzer.analysis.calculator import latest_snapshot
        snap.update({k: v for k, v in latest_snapshot(df).items()
                     if k.startswith("prox_")})

    # Historical ranks
    historical: dict = {}
    if cfg.show_historical_table:
        try:
            historical = compute_historical_ranks(
                df,
                periods    = cfg.historical_periods,
                method     = cfg.analysis_method,
                primary_lb = snap["primary_lookback"],
            )
        except Exception:
            pass

    # Signals
    signals = run_signals(snap, cfg)

    # Attach market_state to snap for chart title use
    snap["_market_state"] = signals.get("market_state", "")

    return {
        "name":       instrument.name,
        "snap":       snap,
        "signals":    signals,
        "historical": historical,
        "df":         df,
        "df_price":   df_price,
    }


# ─────────────────────────────────────────────────────────────
# CHART OUTPUT
# ─────────────────────────────────────────────────────────────

def _maybe_save_chart(result: dict, cfg: AppConfig) -> None:
    if not cfg.show_chart:
        return
    try:
        from cot_analyzer.display.charts import save_chart
        snap = result["snap"]
        paths = save_chart(
            df              = result["df"],
            snap            = snap,
            instrument_name = result["name"],
            output_folder   = cfg.output_folder,
            primary_lb      = snap["primary_lookback"],
            secondary_lb    = snap["secondary_lookback"],
            heavy_buyers    = cfg.heavy_buyers_level,
            heavy_sellers   = cfg.heavy_sellers_level,
            chart_type      = cfg.chart_type,
            chart_format    = cfg.chart_format,
            analysis_method = cfg.analysis_method,
            historical      = result.get("historical", {}),
            proximity_lb    = cfg.proximity_lookback_weeks,
            df_price        = result.get("df_price"),
        )
        for p in paths:
            console.print(f"[dim]Chart saved → {p}[/dim]")
    except Exception as exc:
        console.print(f"[yellow]Chart generation failed: {exc}[/yellow]")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cot_analyzer",
        description="Larry Williams COT Analysis — terminal + CSV output",
    )
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).parent,
        help="Project root directory (default: directory containing main.py)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    _configure_logging(args.verbose)
    project_root: Path = args.root.resolve()

    # ── Load config ──────────────────────────────────────────
    try:
        cfg = load_config(project_root)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red bold]Config error:[/red bold] {exc}")
        return 1

    console.print(
        f"\n[bold white]COT Analyzer[/bold white]  "
        f"[dim]{cfg.report_type} · {cfg.analysis_method} · "
        f"{len(cfg.instruments)} instrument(s)[/dim]\n"
    )

    # ── Process instruments ──────────────────────────────────
    raw_cache: dict = {}
    results: list[dict] = []

    for instrument in cfg.instruments:
        console.print(f"[dim]Processing {instrument.name} …[/dim]", end="\r")
        result = _process_instrument(instrument, raw_cache, cfg, project_root)
        if result is None:
            continue

        results.append(result)

        # Display immediately (streaming output)
        display_instrument(
            name       = result["name"],
            snap       = result["snap"],
            signals    = result["signals"],
            historical = result["historical"],
            cfg        = cfg,
        )

        _maybe_save_chart(result, cfg)

    if not results:
        console.print("[red]No instruments could be processed.[/red]")
        return 1

    # ── Export CSV ───────────────────────────────────────────
    export_results(results, cfg.output_mode, cfg.output_folder)

    console.print(f"\n[dim]Done — {len(results)}/{len(cfg.instruments)} instruments processed.[/dim]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
