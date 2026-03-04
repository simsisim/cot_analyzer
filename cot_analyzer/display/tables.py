"""
tables.py
Terminal output using the Rich library.
Renders colored tables for Full and Compact display modes.
No I/O side-effects beyond printing to stdout.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from cot_analyzer.utils.helpers import format_contracts, format_pct


# ─────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────

_console = Console(record=True)


def set_console(c: Console) -> None:
    """Replace the module-level console (called from main.py to share a single recording instance)."""
    global _console
    _console = c


def _idx_color(value: float, heavy_buyers: int, heavy_sellers: int) -> str:
    """Return a Rich color string based on the index level."""
    if value >= heavy_buyers:
        return "bright_green"
    if value <= heavy_sellers:
        return "bright_red"
    mid = (heavy_buyers + heavy_sellers) / 2.0
    if value > mid:
        return "green"
    if value < mid:
        return "red"
    return "white"


def _state_color(state: str) -> str:
    mapping = {
        "STRONG BULLISH":  "bright_green bold",
        "BULLISH":         "green",
        "NEUTRAL BULLISH": "dark_olive_green1",
        "STRONG BEARISH":  "bright_red bold",
        "BEARISH":         "red",
        "NEUTRAL BEARISH": "dark_orange",
        "NEUTRAL":         "white",
    }
    return mapping.get(state, "white")


def _delta_str(value: float) -> str:
    """Format a signed delta with arrow prefix."""
    if value > 0:
        return f"▲ {format_contracts(value)}"
    if value < 0:
        return f"▼ {format_contracts(abs(value))}"
    return "—"


def _confluence_badge(cf: str) -> Text:
    if cf == "BULL":
        return Text("▲ BULL CONFLUENCE", style="bright_green bold")
    if cf == "BEAR":
        return Text("▼ BEAR CONFLUENCE", style="bright_red bold")
    return Text("")


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────

def print_header(instrument_name: str, date: str, market_state: str) -> None:
    state_style = _state_color(market_state)
    title = Text()
    title.append(f"  COT Analyzer  ·  {instrument_name}  ·  {date}  ·  ", style="bold white")
    title.append(market_state, style=state_style)
    title.append("  ")
    _console.print(Panel(title, expand=False, border_style="dim white"))


# ─────────────────────────────────────────────────────────────
# MAIN POSITIONS TABLE
# ─────────────────────────────────────────────────────────────

def print_positions_table(
    snap: dict,
    signals: dict,
    cfg,
    display_mode: str = "Full",
) -> None:
    """Print the primary COT positions table."""
    hb = cfg.heavy_buyers_level
    hs = cfg.heavy_sellers_level

    tbl = Table(
        title="[bold]COT Positions[/bold]",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold dim",
        expand=False,
    )

    tbl.add_column("Group",      style="bold white", width=14)
    tbl.add_column("Net",        justify="right", width=10)
    tbl.add_column("Wk Δ",       justify="right", width=10)
    tbl.add_column("% of OI",    justify="right", width=9)
    tbl.add_column(f"Idx ({snap.get('primary_lookback', '?')}w)", justify="right", width=9)

    if cfg.show_secondary_lookback:
        tbl.add_column(f"Idx ({snap.get('secondary_lookback', '?')}w)", justify="right", width=9)

    if display_mode == "Full":
        tbl.add_column("Long",   justify="right", width=10)
        tbl.add_column("Short",  justify="right", width=10)

    groups = [
        ("Commercial", "comm"),
        ("Large Spec",  "lrg"),
        ("Small Spec",  "sml"),
    ]

    oi = snap.get("open_interest", 0) or 1  # avoid div/0

    for label, key in groups:
        net    = snap.get(f"{key}_net", float("nan"))
        delta  = snap.get(f"{key}_net_delta", float("nan"))
        idx_p  = snap.get(f"{key}_idx_p",  50.0)
        idx_s  = snap.get(f"{key}_idx_s",  50.0)
        raw_pct = (net / oi * 100) if net == net else float("nan")  # NaN check

        col = _idx_color(idx_p, hb, hs)

        row = [
            Text(label, style="bold white"),
            Text(format_contracts(net),    style=col),
            Text(_delta_str(delta),        style="cyan" if delta > 0 else "magenta"),
            Text(format_pct(raw_pct),      style="dim white"),
            Text(f"{idx_p:.1f}%",          style=col),
        ]

        if cfg.show_secondary_lookback:
            col_s = _idx_color(idx_s, hb, hs)
            row.append(Text(f"{idx_s:.1f}%", style=col_s))

        if display_mode == "Full":
            lrg_key = f"{key}_long"
            srt_key = f"{key}_short"
            row.append(Text(format_contracts(snap.get(lrg_key, float("nan"))), style="dim"))
            row.append(Text(format_contracts(snap.get(srt_key, float("nan"))), style="dim"))

        tbl.add_row(*row)

    _console.print(tbl)

    # Confluence badge
    cf = signals.get("confluence", "")
    if cf:
        _console.print(_confluence_badge(cf))
        _console.print()


# ─────────────────────────────────────────────────────────────
# OPEN INTEREST TABLE
# ─────────────────────────────────────────────────────────────

def print_oi_table(snap: dict, cfg) -> None:
    if not cfg.show_oi_analysis:
        return

    tbl = Table(
        title="[bold]Open Interest[/bold]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold dim",
        expand=False,
    )
    tbl.add_column("Metric",  style="bold dim white", width=20)
    tbl.add_column("Value",   justify="right", width=14)

    oi     = snap.get("open_interest", float("nan"))
    oi_chg = snap.get("oi_chg", float("nan"))
    driver = snap.get("oi_driver", "—")

    tbl.add_row("Open Interest",  format_contracts(oi))
    tbl.add_row("Week Change",    _delta_str(oi_chg))
    tbl.add_row("OI Driver",      str(driver).upper())

    if cfg.show_concentration:
        tbl.add_row("Top-4 Long",  format_pct(snap.get("conc_top4_long", float("nan"))))
        tbl.add_row("Top-4 Short", format_pct(snap.get("conc_top4_short", float("nan"))))
        tbl.add_row("Top-8 Long",  format_pct(snap.get("conc_top8_long", float("nan"))))
        tbl.add_row("Top-8 Short", format_pct(snap.get("conc_top8_short", float("nan"))))

    _console.print(tbl)


# ─────────────────────────────────────────────────────────────
# HISTORICAL RANKS TABLE
# ─────────────────────────────────────────────────────────────

def print_historical_table(historical: dict, cfg) -> None:
    if not cfg.show_historical_table or not historical:
        return

    tbl = Table(
        title="[bold]Historical Percentile Ranks[/bold]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold dim",
        expand=False,
    )
    tbl.add_column("Period",        style="bold dim white", width=10)
    tbl.add_column("Commercial %",  justify="right", width=13)
    tbl.add_column("Non-Comm %",    justify="right", width=11)
    tbl.add_column("Small Spec %",  justify="right", width=12)
    tbl.add_column("Open Int %",    justify="right", width=11)

    for label, ranks in historical.items():
        comm_r = ranks.get("comm", float("nan"))
        lrg_r  = ranks.get("lrg",  float("nan"))
        sml_r  = ranks.get("sml",  float("nan"))
        oi_r   = ranks.get("oi",   float("nan"))

        def _rank_cell(v: float) -> Text:
            s = f"{v:.1f}%" if v == v else "—"
            color = "bright_green" if v >= 75 else ("bright_red" if v <= 25 else "white")
            return Text(s, style=color)

        tbl.add_row(
            label,
            _rank_cell(comm_r),
            _rank_cell(lrg_r),
            _rank_cell(sml_r),
            _rank_cell(oi_r),
        )

    _console.print(tbl)


# ─────────────────────────────────────────────────────────────
# TREND TABLE
# ─────────────────────────────────────────────────────────────

def print_trend_table(snap: dict, cfg) -> None:
    if not cfg.show_trend_analysis:
        return

    tbl = Table(
        title="[bold]Commercial Trend[/bold]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold dim",
        expand=False,
    )
    tbl.add_column("Metric", style="bold dim white", width=20)
    tbl.add_column("Value",  justify="right", width=14)

    vs_ma  = snap.get("comm_vs_ma",   float("nan"))
    roc_4  = snap.get("comm_roc_4w",  float("nan"))
    roc_13 = snap.get("comm_roc_13w", float("nan"))

    tbl.add_row("vs 13w MA",    format_contracts(vs_ma))
    tbl.add_row("RoC 4w (%)",   format_pct(roc_4))
    tbl.add_row("RoC 13w (%)",  format_pct(roc_13))

    for col in ("4W", "13W", "26W"):
        key = f"comm_cum_{col}"
        val = snap.get(key)
        if val is not None:
            tbl.add_row(f"Cum Δ {col}", format_contracts(val))

    _console.print(tbl)


# ─────────────────────────────────────────────────────────────
# MARKET MAKER TABLE
# ─────────────────────────────────────────────────────────────

def print_market_maker_table(snap: dict, cfg) -> None:
    if not cfg.show_market_maker:
        return

    tbl = Table(
        title="[bold]Market Maker (Spreading)[/bold]",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold dim",
        expand=False,
    )
    tbl.add_column("Metric",  style="bold dim white", width=20)
    tbl.add_column("Value",   justify="right", width=14)

    sp_pct  = snap.get("spreading_pct",   float("nan"))
    sp_vs   = snap.get("spreading_vs_ma", float("nan"))

    tbl.add_row("Spreading % of OI", format_pct(sp_pct))
    tbl.add_row("vs 13w MA",         format_contracts(sp_vs))

    _console.print(tbl)


# ─────────────────────────────────────────────────────────────
# SIGNAL SUMMARY PANEL
# ─────────────────────────────────────────────────────────────

def print_signal_panel(signals: dict, cfg) -> None:
    if not cfg.show_market_state:
        return

    lines: list[Text] = []

    state = signals.get("market_state", "NEUTRAL")
    lines.append(Text(f"Market State: ", style="bold white") + Text(state, style=_state_color(state)))

    setup = signals.get("setup", "")
    if setup and cfg.show_best_setup:
        lines.append(Text(f"Best Setup:   {setup}", style="yellow bold"))

    tips = signals.get("tips", [])
    if tips and cfg.show_trading_tips:
        lines.append(Text(""))
        lines.append(Text("Trading Tips:", style="bold dim white"))
        for tip in tips:
            lines.append(Text(f"  · {tip}", style="dim white"))

    if lines:
        content = Text("\n").join(lines)
        _console.print(Panel(content, title="[bold]Signals[/bold]", expand=False, border_style="dim cyan"))


# ─────────────────────────────────────────────────────────────
# COMPACT MODE
# ─────────────────────────────────────────────────────────────

def print_compact(snap: dict, signals: dict, cfg) -> None:
    """One-line summary per instrument for Compact mode."""
    name   = snap.get("market_name", snap.get("cftc_code", "?"))
    date   = snap.get("date", "?")
    state  = signals.get("market_state", "NEUTRAL")
    cf     = signals.get("confluence", "")
    comm_p = snap.get("comm_idx_p", float("nan"))
    lrg_p  = snap.get("lrg_idx_p",  float("nan"))

    cf_tag = f" [{cf}]" if cf else ""
    line = Text()
    line.append(f"{name:<25}", style="bold white")
    line.append(f" {date}  ", style="dim white")
    line.append(f"Comm={comm_p:.0f}%  Lrg={lrg_p:.0f}%  ", style="white")
    line.append(f"{state}{cf_tag}", style=_state_color(state))
    _console.print(line)


# ─────────────────────────────────────────────────────────────
# FULL DISPLAY ORCHESTRATOR
# ─────────────────────────────────────────────────────────────

def display_instrument(
    name: str,
    snap: dict,
    signals: dict,
    historical: dict,
    cfg,
) -> None:
    """
    Render all enabled sections for one instrument.
    Dispatches to Full or Compact based on cfg.display_mode.
    """
    _console.rule(f"[bold white]{name}[/bold white]")

    if cfg.display_mode == "Compact":
        print_compact(snap, signals, cfg)
        return

    # Full mode
    print_header(name, snap.get("date", "?"), signals.get("market_state", "NEUTRAL"))
    print_positions_table(snap, signals, cfg, display_mode="Full")
    print_signal_panel(signals, cfg)
    print_oi_table(snap, cfg)
    print_historical_table(historical, cfg)
    print_trend_table(snap, cfg)
    print_market_maker_table(snap, cfg)
    _console.print()
