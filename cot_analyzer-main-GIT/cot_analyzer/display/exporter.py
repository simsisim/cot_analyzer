"""
exporter.py
Writes analysis results to CSV files in the output folder.
Two outputs:
  1. summary.csv      — one row per instrument (latest snapshot + signals)
  2. <name>_ts.csv    — full time-series for each instrument (if requested)
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _output_dir(output_folder: Path) -> Path:
    output_folder.mkdir(parents=True, exist_ok=True)
    return output_folder


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


# ─────────────────────────────────────────────────────────────
# SUMMARY CSV (all instruments, one row each)
# ─────────────────────────────────────────────────────────────

_SUMMARY_FIELDS = [
    "instrument",
    "date",
    "market_state",
    "confluence",
    "setup",
    "comm_idx_p",
    "lrg_idx_p",
    "sml_idx_p",
    "comm_net",
    "lrg_net",
    "sml_net",
    "open_interest",
    "oi_driver",
    "spreading_pct",
    "primary_lookback",
    "secondary_lookback",
]


def write_summary_csv(
    rows: list[dict],
    output_folder: Path,
) -> Path:
    """
    Append (or create) the run summary CSV.

    Parameters
    ----------
    rows : list of dicts, one per instrument, with keys from _SUMMARY_FIELDS
    output_folder : destination directory

    Returns
    -------
    Path to the summary CSV file.
    """
    out_dir = _output_dir(output_folder)
    path = out_dir / "summary.csv"
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["run_ts"] + _SUMMARY_FIELDS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        ts = _timestamp()
        for row in rows:
            writer.writerow({"run_ts": ts, **row})

    return path


# ─────────────────────────────────────────────────────────────
# TIME-SERIES CSV (one file per instrument)
# ─────────────────────────────────────────────────────────────

def write_timeseries_csv(
    df: pd.DataFrame,
    instrument_name: str,
    output_folder: Path,
) -> Path:
    """
    Write the full enriched DataFrame to a CSV file.

    Parameters
    ----------
    df              : enriched DataFrame from calculator.run_calculations()
    instrument_name : used for the filename
    output_folder   : destination directory

    Returns
    -------
    Path to the time-series CSV file.
    """
    out_dir = _output_dir(output_folder / "timeseries")
    safe    = "".join(c if c.isalnum() or c in "-_" else "_" for c in instrument_name)
    path    = out_dir / f"{safe}.csv"
    df.to_csv(path, index=False, float_format="%.4f")
    return path


# ─────────────────────────────────────────────────────────────
# PUBLIC ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

def export_results(
    results: list[dict],
    output_mode: str,
    output_folder: Path,
) -> None:
    """
    Route results to CSV output based on output_mode setting.

    Parameters
    ----------
    results     : list of result dicts, each containing:
                    'name', 'snap', 'signals', 'df'
    output_mode : 'terminal' | 'csv' | 'both'
    output_folder
    """
    if output_mode == "terminal":
        return

    summary_rows: list[dict] = []

    for r in results:
        name    = r["name"]
        snap    = r["snap"]
        signals = r["signals"]
        df      = r.get("df")

        row = {
            "instrument":       name,
            "date":             snap.get("date"),
            "market_state":     signals.get("market_state"),
            "confluence":       signals.get("confluence", ""),
            "setup":            signals.get("setup", ""),
            "comm_idx_p":       round(snap.get("comm_idx_p", float("nan")), 2),
            "lrg_idx_p":        round(snap.get("lrg_idx_p",  float("nan")), 2),
            "sml_idx_p":        round(snap.get("sml_idx_p",  float("nan")), 2),
            "comm_net":         snap.get("comm_net"),
            "lrg_net":          snap.get("lrg_net"),
            "sml_net":          snap.get("sml_net"),
            "open_interest":    snap.get("open_interest"),
            "oi_driver":        snap.get("oi_driver", ""),
            "spreading_pct":    round(snap.get("spreading_pct", float("nan")), 2),
            "primary_lookback": snap.get("primary_lookback"),
            "secondary_lookback": snap.get("secondary_lookback"),
        }
        summary_rows.append(row)

        # Per-instrument time-series
        if df is not None:
            write_timeseries_csv(df, name, output_folder)

    if summary_rows:
        path = write_summary_csv(summary_rows, output_folder)
        from rich.console import Console
        Console().print(f"[dim]CSV summary → {path}[/dim]")
