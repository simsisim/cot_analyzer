"""
latex_report.py
Renders a multi-instrument COT summary PDF via Jinja2 + xelatex.

Entry point:
    generate_latex_report(results, cfg, output_folder) -> Path
"""

from __future__ import annotations

import math
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cot_analyzer.utils.helpers import format_contracts


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

_LATEX_SPECIAL = {
    "&":  r"\&",
    "%":  r"\%",
    "$":  r"\$",
    "#":  r"\#",
    "_":  r"\_",
    "{":  r"\{",
    "}":  r"\}",
    "~":  r"\textasciitilde{}",
    "^":  r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIAL))


def _latex_escape(text: str) -> str:
    return _ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL[m.group()], str(text))


def _basename(path: str) -> str:
    return Path(path).name


def _fmt(val: Any, decimals: int = 1) -> str:
    """Format a numeric value; return '--' for None/NaN."""
    try:
        if val is None:
            return "--"
        f = float(val)
        if math.isnan(f):
            return "--"
        return f"{f:.{decimals}f}"
    except (TypeError, ValueError):
        return str(val) if val is not None else "--"


def _fmt_k(val: Any) -> str:
    """Format as K/M contract string; return '--' for None/NaN."""
    try:
        f = float(val)
        if math.isnan(f):
            return "--"
        return format_contracts(f)
    except (TypeError, ValueError):
        return "--"


def _fmt_delta(val: Any) -> str:
    """Return '+12.3K' / '-4.0K' / '--' for a signed delta value."""
    try:
        f = float(val)
        if math.isnan(f):
            return "--"
        prefix = "+" if f >= 0 else ""
        return prefix + format_contracts(f)
    except (TypeError, ValueError):
        return "--"


def _idx_latex_color(val: Any, heavy_buyers: int = 74, heavy_sellers: int = 26) -> str:
    """Return LaTeX color name (bullish/bearish/neutral) for an index % value."""
    try:
        v = float(val)
        if math.isnan(v):
            return "neutral"
        if v >= heavy_buyers:
            return "bullish"
        if v <= heavy_sellers:
            return "bearish"
        return "neutral"
    except (TypeError, ValueError):
        return "neutral"


# ─────────────────────────────────────────────────────────────
# DATA EXTRACTION
# ─────────────────────────────────────────────────────────────

def _extract_result_data(result: dict, output_folder: Path) -> dict:
    """Pull display-ready fields from a pipeline result dict."""
    snap = result.get("snap", {})
    signals = result.get("signals", {})
    historical = result.get("historical", {})
    name = result.get("name", "Unknown")

    # Collect PNG charts that exist for this instrument
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", name)
    charts_dir = output_folder / "charts" / safe
    charts: list[str] = []
    if charts_dir.exists():
        for p in sorted(charts_dir.glob("*.png")):
            charts.append(str(p.resolve()))

    # Format historical ranks — include oi_pct column
    hist_rows: dict[str, dict] = {}
    for period, data in historical.items():
        hist_rows[period] = {
            "comm_pct": _fmt(data.get("comm")),
            "ls_pct":   _fmt(data.get("lrg")),
            "ss_pct":   _fmt(data.get("sml")),
            "oi_pct":   _fmt(data.get("oi")),
        }

    confluence_val = signals.get("confluence", "")

    # OI driver label mapping
    _oi_driver_map = {"comm": "COMM", "lrg": "LRG SPEC", "sml": "SML SPEC"}
    raw_driver = snap.get("oi_driver", "")
    oi_driver_label = _oi_driver_map.get(str(raw_driver), str(raw_driver) if raw_driver else "--")

    return {
        # Header
        "name":         name,
        "date":         snap.get("date", ""),
        "market_state": signals.get("market_state", ""),
        "confluence":   confluence_val,   # 'BULL' | 'BEAR' | ''
        "best_setup":   signals.get("setup", ""),
        "tips":         signals.get("tips", []),

        # Legacy fields (kept for backward compat)
        "willco_pct":           _fmt(snap.get("comm_willco_raw")),
        "comm_index_primary":   _fmt(snap.get("comm_idx_p")),
        "comm_index_secondary": _fmt(snap.get("comm_idx_s")),
        "ls_index_primary":     _fmt(snap.get("lrg_idx_p")),
        "signal":               signals.get("setup", ""),

        # COT Positions table (3 rows)
        "positions": [
            {
                "group":       "Commercial",
                "net":         _fmt_k(snap.get("comm_net")),
                "delta":       _fmt_delta(snap.get("comm_net_delta")),
                "pct_oi":      _fmt(snap.get("comm_willco_raw"), 1),
                "idx_p":       _fmt(snap.get("comm_idx_p"), 1),
                "idx_s":       _fmt(snap.get("comm_idx_s"), 1),
                "long":        _fmt_k(snap.get("comm_long")),
                "short":       _fmt_k(snap.get("comm_short")),
                "idx_p_color": _idx_latex_color(snap.get("comm_idx_p")),
                "idx_s_color": _idx_latex_color(snap.get("comm_idx_s")),
            },
            {
                "group":       "Large Spec",
                "net":         _fmt_k(snap.get("lrg_net")),
                "delta":       _fmt_delta(snap.get("lrg_net_delta")),
                "pct_oi":      _fmt(snap.get("lrg_willco_raw"), 1),
                "idx_p":       _fmt(snap.get("lrg_idx_p"), 1),
                "idx_s":       _fmt(snap.get("lrg_idx_s"), 1),
                "long":        _fmt_k(snap.get("lrg_long")),
                "short":       _fmt_k(snap.get("lrg_short")),
                "idx_p_color": _idx_latex_color(snap.get("lrg_idx_p")),
                "idx_s_color": _idx_latex_color(snap.get("lrg_idx_s")),
            },
            {
                "group":       "Small Spec",
                "net":         _fmt_k(snap.get("sml_net")),
                "delta":       _fmt_delta(snap.get("sml_net_delta")),
                "pct_oi":      _fmt(snap.get("sml_willco_raw"), 1),
                "idx_p":       _fmt(snap.get("sml_idx_p"), 1),
                "idx_s":       _fmt(snap.get("sml_idx_s"), 1),
                "long":        _fmt_k(snap.get("sml_long")),
                "short":       _fmt_k(snap.get("sml_short")),
                "idx_p_color": _idx_latex_color(snap.get("sml_idx_p")),
                "idx_s_color": _idx_latex_color(snap.get("sml_idx_s")),
            },
        ],
        "primary_lb":   snap.get("primary_lookback", 13),
        "secondary_lb": snap.get("secondary_lookback", 52),

        # Open Interest section
        "oi": {
            "open_interest": _fmt_k(snap.get("open_interest")),
            "oi_chg":        _fmt_delta(snap.get("oi_chg")),
            "oi_driver":     oi_driver_label,
            "top4_long":     _fmt(snap.get("conc_top4_long"), 1),
            "top4_short":    _fmt(snap.get("conc_top4_short"), 1),
            "top8_long":     _fmt(snap.get("conc_top8_long"), 1),
            "top8_short":    _fmt(snap.get("conc_top8_short"), 1),
        },

        # Commercial Trend section
        "trend": {
            "vs_ma":   _fmt_k(snap.get("comm_vs_ma")),
            "roc_4w":  _fmt(snap.get("comm_roc_4w"), 1),
            "roc_13w": _fmt(snap.get("comm_roc_13w"), 1),
            "cum_4w":  _fmt_k(snap.get("comm_cum_4W")),
            "cum_13w": _fmt_k(snap.get("comm_cum_13W")),
            "cum_26w": _fmt_k(snap.get("comm_cum_26W")),
        },

        # Market Maker section
        "market_maker": {
            "spreading_pct": _fmt(snap.get("spreading_pct"), 1),
            "vs_ma":         _fmt_k(snap.get("spreading_vs_ma")),
        },

        # Historical ranks (with oi_pct)
        "historical": hist_rows,

        # Charts
        "charts": charts,
    }


# ─────────────────────────────────────────────────────────────
# TEMPLATE RENDERING
# ─────────────────────────────────────────────────────────────

def _render_tex(results: list[dict], cfg: Any, output_folder: Path) -> str:
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape([]),  # LaTeX — no HTML escaping
        variable_start_string="{{",
        variable_end_string="}}",
        block_start_string="{%",
        block_end_string="%}",
        comment_start_string="{#",
        comment_end_string="#}",
    )
    env.filters["latex_escape"] = _latex_escape
    env.filters["basename"] = _basename

    template = env.get_template("cot_report.tex.j2")

    result_data = [_extract_result_data(r, output_folder) for r in results]

    return template.render(
        report_date=date.today().isoformat(),
        report_type=cfg.report_type,
        analysis_method=cfg.analysis_method,
        instruments=[r["name"] for r in result_data],
        results=result_data,
    )


# ─────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────

def generate_latex_report(
    results: list[dict],
    cfg: Any,
    output_folder: Path,
) -> Path:
    """
    Render a .tex file from results and compile it with xelatex.

    Returns the path to the generated PDF.
    Raises RuntimeError if xelatex is not found or compilation fails.
    """
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    tex_path = output_folder / "cot_report.tex"
    pdf_path = output_folder / "cot_report.pdf"

    tex_source = _render_tex(results, cfg, output_folder)
    tex_path.write_text(tex_source, encoding="utf-8")

    # Run xelatex twice for correct TOC/cross-refs
    cmd = [
        "xelatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_folder}",
        str(tex_path),
    ]
    for _ in range(2):
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            log_path = output_folder / "cot_report.log"
            log_snippet = ""
            if log_path.exists():
                # Show last 40 lines of the log for diagnostics
                lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                log_snippet = "\n".join(lines[-40:])
            raise RuntimeError(
                f"xelatex failed (exit {proc.returncode}).\n"
                f"--- last 40 log lines ---\n{log_snippet}\n"
                f"--- stderr ---\n{proc.stderr}"
            )

    if not pdf_path.exists():
        raise RuntimeError(f"xelatex ran but {pdf_path} was not created.")

    return pdf_path
