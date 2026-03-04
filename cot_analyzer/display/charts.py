"""
charts.py
Generates interactive HTML charts using Plotly, matching the tradeviZion style:

  COT_Report   — raw net positions (Long/Short/Net) + OI on secondary axis
  COT_Index    — normalized index (LW_Index 0-100%, Percentile -20/+120%,
                 or Both with solid=LW + dashed=Percentile on same panel)
  COT_Proximity— price-based proxy (Commercial inverted, Specs aligned)

Layout per chart:
  Left 75%  : COT indicator lines
  Right 25% : Historical ranks table (5 cols × 6 rows)

Color convention (matches TradingView PNGs):
    Commercial  → teal-green  (#26a69a)
    Large Spec  → blue        (#2196F3)
    Small Spec  → red         (#ef5350)
    Open Interest → gray      (#90a4ae)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────────────────────
# PALETTE
# ─────────────────────────────────────────────────────────────

_C_COMM = "#26a69a"
_C_LRG  = "#2196F3"
_C_SML  = "#ef5350"
_C_OI   = "#90a4ae"
_C_BULL = "#26a69a"
_C_BEAR = "#ef5350"
_C_NEU  = "#888888"
_BG     = "#131722"
_PANEL  = "#1e222d"

# Group metadata: key → (df_column, display_label, line_color)
_GROUP_DEFS = {
    "comm": ("comm_net", "Commercials",                _C_COMM),
    "lrg":  ("lrg_net",  "Large Spec (Non-Commercial)", _C_LRG),
    "sml":  ("sml_net",  "Small Spec (Non-Reportable)", _C_SML),
}


def _sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def _rank_color(v: float) -> str:
    if pd.isna(v):
        return _C_NEU
    if v >= 75:
        return _C_BULL
    if v <= 25:
        return _C_BEAR
    return "#cccccc"


def _val_annotation(fig, x, y, text: str, color: str, row: int, col: int):
    """Add a current-value label at the rightmost point of a line."""
    fig.add_annotation(
        x=x, y=y,
        text=f" {text}",
        showarrow=False,
        xanchor="left",
        font=dict(color=color, size=9),
        row=row, col=col,
    )


# ─────────────────────────────────────────────────────────────
# HISTORICAL TABLE TRACE  (5 columns × 6 rows)
# ─────────────────────────────────────────────────────────────

def _build_table_trace(historical: dict, go):
    """
    Build a Plotly Table with exactly:
      Columns : Period | Commercial % | Non-Comm % | Small Spec % | Open Int %
      Rows    : 1M | 3M | 6M | 1Y | 3Y | All (whatever is in historical dict)
    """
    periods     = list(historical.keys())
    comm_v, lrg_v, sml_v, oi_v         = [], [], [], []
    comm_c, lrg_c, sml_c, oi_c         = [], [], [], []

    for p in periods:
        r = historical.get(p, {})
        for vals, colors, key in (
            (comm_v, comm_c, "comm"),
            (lrg_v,  lrg_c,  "lrg"),
            (sml_v,  sml_c,  "sml"),
            (oi_v,   oi_c,   "oi"),
        ):
            v = r.get(key, float("nan"))
            vals.append(f"{v:.1f}%" if v == v else "—")
            colors.append(_rank_color(v))

    return go.Table(
        columnwidth=[50, 62, 60, 65, 60],
        header=dict(
            values=["Period", "Commercial %", "Non-Comm %", "Small Spec %", "Open Int %"],
            fill_color=_BG,
            font=dict(color="#aaaaaa", size=10),
            align="center",
            height=22,
        ),
        cells=dict(
            values=[periods, comm_v, lrg_v, sml_v, oi_v],
            fill_color=[[_PANEL] * len(periods), comm_c, lrg_c, sml_c, oi_c],
            font=dict(color="#ffffff", size=10),
            align="center",
            height=20,
        ),
    )


# ─────────────────────────────────────────────────────────────
# SHARED LAYOUT
# ─────────────────────────────────────────────────────────────

def _apply_layout(fig, title: str, snap: dict, y_label: str,
                  secondary_label: str | None = None):
    state = snap.get("_market_state", "")
    date  = snap.get("date", "")
    full_title = f"{title}  ·  {date}  ·  {state}"

    fig.update_layout(
        title=dict(text=full_title, font=dict(size=13, color="#cccccc"), x=0.01),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=480,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=55, r=10, t=60, b=40),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", showgrid=True, row=1, col=1)
    fig.update_yaxes(
        title_text=y_label,
        gridcolor="rgba(255,255,255,0.05)",
        showgrid=True,
        row=1, col=1,
        secondary_y=False,
    )
    if secondary_label:
        fig.update_yaxes(
            title_text=secondary_label,
            showgrid=False,
            row=1, col=1,
            secondary_y=True,
        )


# ─────────────────────────────────────────────────────────────
# COT REPORT CHART  (raw net positions)
# ─────────────────────────────────────────────────────────────

def _build_cot_report(df, snap, name, go, make_subplots,
                      historical, heavy_buyers, heavy_sellers):
    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.75, 0.25],
        specs=[[{"secondary_y": True}, {"type": "table"}]],
        horizontal_spacing=0.02,
    )
    dates = df["date"]

    for col, label, color in (
        ("comm_net", "Commercial Net", _C_COMM),
        ("lrg_net",  "Non-Comm Net",   _C_LRG),
        ("sml_net",  "Small Spec Net", _C_SML),
    ):
        if col not in df.columns:
            continue
        last_val = df[col].iloc[-1]
        fig.add_trace(go.Scatter(
            x=dates, y=df[col], name=label,
            line=dict(color=color, width=1.5),
            hovertemplate=f"{label}: %{{y:,.0f}}<extra></extra>",
        ), row=1, col=1, secondary_y=False)
        _val_annotation(fig, dates.iloc[-1], last_val, f"{last_val:,.0f}", color, 1, 1)

    if "open_interest" in df.columns:
        fig.add_trace(go.Scatter(
            x=dates, y=df["open_interest"], name="Open Interest",
            line=dict(color=_C_OI, width=1, dash="dot"), opacity=0.6,
            hovertemplate="OI: %{y:,.0f}<extra></extra>",
        ), row=1, col=1, secondary_y=True)

    fig.add_hline(y=0, row=1, col=1,
                  line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dash"))

    if historical:
        fig.add_trace(_build_table_trace(historical, go), row=1, col=2)

    _apply_layout(fig, f"{name} — COT Report (Raw Positions)",
                  snap, "Contracts", secondary_label="Open Interest")
    return fig


# ─────────────────────────────────────────────────────────────
# COT INDEX CHART  (LW_Index | Percentile | Both)
# ─────────────────────────────────────────────────────────────

def _build_cot_index(df, snap, name, go, make_subplots,
                     historical, heavy_buyers, heavy_sellers,
                     primary_lb, secondary_lb, analysis_method):

    is_both       = analysis_method == "WillCo"
    is_percentile = analysis_method == "Percentile"
    y_range       = [-25, 125] if (is_percentile or is_both) else [-5, 105]
    method_label  = "WillCo (LW + Percentile)" if is_both else analysis_method.replace("_", " ")

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.75, 0.25],
        specs=[[{"secondary_y": False}, {"type": "table"}]],
        horizontal_spacing=0.02,
    )
    dates = df["date"]

    if is_both:
        # ── Solid = LW_Index, dashed = Percentile ─────────────
        for col_lw, col_pct, label, color in (
            ("comm_idx_p_lw", "comm_idx_p_pct", f"Commercial ({primary_lb}w)", _C_COMM),
            ("lrg_idx_p_lw",  "lrg_idx_p_pct",  f"Non-Comm ({primary_lb}w)",   _C_LRG),
            ("sml_idx_p_lw",  "sml_idx_p_pct",  f"Small Spec ({primary_lb}w)", _C_SML),
        ):
            for col, dash, suffix_label, width in (
                (col_lw,  "solid", "LW",  1.8),
                (col_pct, "dash",  "Pct", 1.2),
            ):
                if col not in df.columns:
                    continue
                last_val = df[col].iloc[-1]
                fig.add_trace(go.Scatter(
                    x=dates, y=df[col],
                    name=f"{label} {suffix_label}",
                    line=dict(color=color, width=width, dash=dash),
                    opacity=1.0 if dash == "solid" else 0.65,
                    hovertemplate=f"{label} {suffix_label}: %{{y:.1f}}%<extra></extra>",
                ), row=1, col=1)
                if dash == "solid":
                    _val_annotation(fig, dates.iloc[-1], last_val,
                                    f"{last_val:.3f}", color, 1, 1)
    else:
        # ── Single method — primary + secondary lookback ───────
        for col, label, color in (
            (f"comm_idx_p", f"Commercial ({primary_lb}w)", _C_COMM),
            (f"lrg_idx_p",  f"Non-Comm ({primary_lb}w)",   _C_LRG),
            (f"sml_idx_p",  f"Small Spec ({primary_lb}w)", _C_SML),
        ):
            if col not in df.columns:
                continue
            last_val = df[col].iloc[-1]
            fig.add_trace(go.Scatter(
                x=dates, y=df[col], name=label,
                line=dict(color=color, width=1.8),
                hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
            ), row=1, col=1)
            _val_annotation(fig, dates.iloc[-1], last_val,
                            f"{last_val:.3f}", color, 1, 1)

        # Secondary lookback (dotted, faded)
        for col, label, color in (
            (f"comm_idx_s", f"Commercial ({secondary_lb}w)", _C_COMM),
            (f"lrg_idx_s",  f"Non-Comm ({secondary_lb}w)",   _C_LRG),
        ):
            if col not in df.columns:
                continue
            fig.add_trace(go.Scatter(
                x=dates, y=df[col], name=label,
                line=dict(color=color, width=1, dash="dot"),
                opacity=0.4,
                hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
            ), row=1, col=1)

    # Reference lines
    for level, label, alpha, dash in (
        (heavy_buyers,  f"Heavy Buyers ({heavy_buyers}%)",   0.35, "dash"),
        (heavy_sellers, f"Heavy Sellers ({heavy_sellers}%)", 0.35, "dash"),
        (100,           "100",   0.2,  "dot"),
        (0,             "0",     0.2,  "dot"),
        (50,            "",      0.1,  "dot"),
    ):
        fig.add_hline(
            y=level, row=1, col=1,
            line=dict(color=f"rgba(255,255,255,{alpha})", width=1, dash=dash),
            annotation_text=label,
            annotation_position="right",
            annotation_font=dict(size=9, color="#777777"),
        )

    if historical:
        fig.add_trace(_build_table_trace(historical, go), row=1, col=2)

    if is_both:
        subtitle = "WillCo: Solid = LW Index (0–100%)  ·  Dashed = Percentile (can exceed 0–100%)"
    elif is_percentile:
        subtitle = "Percentile can exceed 0–100% for extremes"
    else:
        subtitle = "LW Index stays 0–100%"

    _apply_layout(fig, f"{name} — COT Index ({method_label})  |  {subtitle}", snap, "Index %")
    fig.update_yaxes(range=y_range, row=1, col=1)
    return fig


# ─────────────────────────────────────────────────────────────
# COT PROXIMITY CHART  (price-based proxy)
# ─────────────────────────────────────────────────────────────

def _build_cot_proximity(df, snap, name, go, make_subplots,
                         historical, heavy_buyers, heavy_sellers,
                         proximity_lb):

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.75, 0.25],
        specs=[[{"secondary_y": False}, {"type": "table"}]],
        horizontal_spacing=0.02,
    )
    dates = df["date"]

    has_data = any(c in df.columns for c in ("prox_comm", "prox_lrg", "prox_sml"))

    if has_data:
        for col, label, color in (
            ("prox_comm", f"Commercial Proxy ({proximity_lb}w)", _C_COMM),
            ("prox_lrg",  f"Non-Comm Proxy ({proximity_lb}w)",   _C_LRG),
            ("prox_sml",  f"Small Spec Proxy ({proximity_lb}w)", _C_SML),
        ):
            if col not in df.columns:
                continue
            last_val = df[col].iloc[-1]
            if pd.isna(last_val):
                continue
            fig.add_trace(go.Scatter(
                x=dates, y=df[col], name=label,
                line=dict(color=color, width=1.8),
                hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
            ), row=1, col=1)
            _val_annotation(fig, dates.iloc[-1], last_val,
                            f"{last_val:.1f}%", color, 1, 1)
    else:
        # No price data — show a placeholder annotation
        fig.add_annotation(
            text="No price data available.<br>Set the 'ticker' column in instruments.csv.",
            xref="paper", yref="paper", x=0.375, y=0.5,
            showarrow=False,
            font=dict(color="#aaaaaa", size=13),
            align="center",
        )

    # Reference lines
    for level, label, alpha in (
        (heavy_buyers,  f"Heavy Buyers ({heavy_buyers}%)",   0.35),
        (heavy_sellers, f"Heavy Sellers ({heavy_sellers}%)", 0.35),
        (100, "100", 0.2),
        (50,  "",    0.1),
        (0,   "0",   0.2),
    ):
        fig.add_hline(
            y=level, row=1, col=1,
            line=dict(color=f"rgba(255,255,255,{alpha})", width=1, dash="dash"),
            annotation_text=label,
            annotation_position="right",
            annotation_font=dict(size=9, color="#777777"),
        )

    if historical:
        fig.add_trace(_build_table_trace(historical, go), row=1, col=2)

    _apply_layout(
        fig,
        f"{name} — COT Proximity Index  |  ⚠ Proxy only — based on price, not actual COT positions",
        snap, "Index %",
    )
    fig.update_yaxes(range=[-5, 105], row=1, col=1)
    return fig


# ─────────────────────────────────────────────────────────────
# FIGURE A  (3-panel: candlestick + CFTC % of OI + Pct_Long)
# ─────────────────────────────────────────────────────────────

def _build_figure_a(df, snap, name, df_price, go, make_subplots,
                    heavy_buyers, heavy_sellers):
    """
    5-panel PNG-oriented chart:
      Panel 1 (30%) — Weekly candlestick price (yfinance OHLCV)
      Panel 2 (17%) — CFTC % of Open Interest (long% solid, short% dashed)
      Panel 3 (17%) — Pct_Long = long/(long+short)×100 per group
      Panel 4 (18%) — Net positions in contracts (comm/lrg/sml + OI on secondary y)
      Panel 5 (18%) — Commercial net only, zero line (Larry Williams style)
    """
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        row_heights=[0.30, 0.17, 0.17, 0.18, 0.18],
        vertical_spacing=0.03,
        specs=[
            [{}],
            [{}],
            [{}],
            [{"secondary_y": True}],
            [{}],
        ],
        subplot_titles=[
            f"{name} — Weekly Price",
            "CFTC % of Open Interest  (solid = Long, dashed = Short)",
            "Pct Long  [long / (long + short) × 100]",
            "Net Positions — All Groups (contracts)",
            "Commercial Net Position  (Larry Williams style)",
        ],
    )

    # Convert all dates to ISO strings for reliable Plotly date rendering
    cot_dates = df["date"].dt.strftime("%Y-%m-%d")

    # ── Panel 1: Candlestick ──────────────────────────────────
    has_price = df_price is not None and not df_price.empty
    req = {"date", "open", "high", "low", "close"}
    if has_price and req.issubset(df_price.columns):
        price_dates = df_price["date"].dt.strftime("%Y-%m-%d")
        fig.add_trace(go.Candlestick(
            x=price_dates,
            open=df_price["open"],
            high=df_price["high"],
            low=df_price["low"],
            close=df_price["close"],
            name="Price",
            increasing_line_color=_C_BULL,
            decreasing_line_color=_C_BEAR,
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_annotation(
            text="No price data — set 'ticker' in instruments.csv",
            xref="paper", yref="y1", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panel 2: CFTC % of OI ────────────────────────────────
    oi = df["open_interest"].replace(0, float("nan"))

    for raw_col, label, color, dash in (
        ("comm_long",  "Commercial Long %",   _C_COMM, "solid"),
        ("comm_short", "Commercial Short %",  _C_COMM, "dash"),
        ("lrg_long",   "Non-Comm Long %",     _C_LRG,  "solid"),
        ("lrg_short",  "Non-Comm Short %",    _C_LRG,  "dash"),
        ("sml_long",   "Small Spec Long %",   _C_SML,  "solid"),
        ("sml_short",  "Small Spec Short %",  _C_SML,  "dash"),
    ):
        if raw_col not in df.columns:
            continue
        pct_oi = df[raw_col] / oi * 100
        last_v = pct_oi.iloc[-1]
        width   = 1.6 if dash == "solid" else 1.0
        opacity = 1.0 if dash == "solid" else 0.65
        fig.add_trace(go.Scatter(
            x=cot_dates, y=pct_oi, name=label,
            line=dict(color=color, width=width, dash=dash),
            opacity=opacity,
            hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
        ), row=2, col=1)
        if dash == "solid":
            _val_annotation(fig, cot_dates.iloc[-1], last_v, f"{last_v:.1f}%", color, 2, 1)

    # ── Panel 3: Pct_Long ────────────────────────────────────
    for col, label, color in (
        ("comm_pct_long", "Commercial Pct Long", _C_COMM),
        ("lrg_pct_long",  "Non-Comm Pct Long",   _C_LRG),
        ("sml_pct_long",  "Small Spec Pct Long",  _C_SML),
    ):
        if col not in df.columns:
            continue
        last_v = df[col].iloc[-1]
        fig.add_trace(go.Scatter(
            x=cot_dates, y=df[col], name=label,
            line=dict(color=color, width=1.8),
            hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
        ), row=3, col=1)
        _val_annotation(fig, cot_dates.iloc[-1], last_v, f"{last_v:.1f}%", color, 3, 1)

    # 50% reference on Panel 3
    fig.add_hline(
        y=50, row=3, col=1,
        line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"),
        annotation_text="50%",
        annotation_position="right",
        annotation_font=dict(size=9, color="#777777"),
    )

    # ── Panel 4: Net positions (contracts) ───────────────────
    for col, label, color in (
        ("comm_net", "Commercial Net", _C_COMM),
        ("lrg_net",  "Non-Comm Net",   _C_LRG),
        ("sml_net",  "Small Spec Net", _C_SML),
    ):
        if col not in df.columns:
            continue
        last_v = df[col].iloc[-1]
        fig.add_trace(go.Scatter(
            x=cot_dates, y=df[col], name=label,
            line=dict(color=color, width=1.6),
            hovertemplate=f"{label}: %{{y:,.0f}}<extra></extra>",
        ), row=4, col=1, secondary_y=False)
        _val_annotation(fig, cot_dates.iloc[-1], last_v, f"{last_v/1000:.0f}K", color, 4, 1)

    # Zero reference line on Panel 4
    fig.add_hline(
        y=0, row=4, col=1,
        line=dict(color="rgba(255,255,255,0.2)", width=1, dash="dash"),
    )

    # Open Interest on secondary y of Panel 4
    if "open_interest" in df.columns:
        fig.add_trace(go.Scatter(
            x=cot_dates, y=df["open_interest"],
            name="Open Interest",
            line=dict(color=_C_OI, width=1, dash="dot"),
            opacity=0.5,
            hovertemplate="OI: %{y:,.0f}<extra></extra>",
        ), row=4, col=1, secondary_y=True)

    # ── Panel 5: Commercial net only (Williams style) ────────
    if "comm_net" in df.columns:
        last_v = df["comm_net"].iloc[-1]
        # Fill above/below zero with different colors
        fig.add_trace(go.Scatter(
            x=cot_dates, y=df["comm_net"],
            name="Commercial Net (P5)",
            line=dict(color=_C_COMM, width=1.8),
            fill="tozeroy",
            fillcolor="rgba(38,166,154,0.15)",
            hovertemplate="Commercial Net: %{y:,.0f}<extra></extra>",
            showlegend=False,
        ), row=5, col=1)
        _val_annotation(fig, cot_dates.iloc[-1], last_v, f"{last_v/1000:.0f}K", _C_COMM, 5, 1)

    fig.add_hline(
        y=0, row=5, col=1,
        line=dict(color="rgba(255,255,255,0.4)", width=1.2, dash="solid"),
    )

    # ── Layout ───────────────────────────────────────────────
    date  = snap.get("date", "")
    state = snap.get("_market_state", "")
    fig.update_layout(
        title=dict(
            text=f"Figure A  ·  {name}  ·  {date}  ·  {state}",
            font=dict(size=13, color="#cccccc"), x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=1300,
        width=1400,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=9),
            bgcolor="rgba(0,0,0,0)",
            traceorder="normal",
        ),
        margin=dict(l=60, r=80, t=70, b=40),
    )

    # Disable candlestick rangeslider (bleeds into next panel with shared_xaxes)
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    # Hide tick labels on all panels except the bottom one
    for r in (1, 2, 3, 4):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.update_xaxes(showticklabels=True, row=5, col=1)

    # Y-axis labels
    gc = "rgba(255,255,255,0.05)"
    fig.update_yaxes(title_text="Price",        row=1, col=1, gridcolor=gc)
    fig.update_yaxes(title_text="% of OI",      row=2, col=1, gridcolor=gc)
    fig.update_yaxes(title_text="Pct Long %",   row=3, col=1, range=[-2, 102], gridcolor=gc)
    fig.update_yaxes(title_text="Contracts",    row=4, col=1, secondary_y=False, gridcolor=gc)
    fig.update_yaxes(title_text="Open Interest",row=4, col=1, secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="Comm Net",     row=5, col=1, gridcolor=gc)

    # Subtitle annotation
    fig.add_annotation(
        text="P2: CFTC raw %OI (long+short ≠ 100%)  ·  "
             "P3: bias within group's own book (50% = neutral)  ·  "
             "P4: net contracts all groups, OI on right axis  ·  "
             "P5: Commercial net only (long − short), above 0 = net long",
        xref="paper", yref="paper", x=0.01, y=-0.03,
        showarrow=False, font=dict(color="#666666", size=9),
        align="left",
    )

    return fig


# ─────────────────────────────────────────────────────────────
# FIGURE B  (Larry Williams Figure 4.1 style)
# Panel 1: price candlestick
# Panel 2: commercial net position bar chart  (green = net long, red = net short)
# Panel 3: COT Commercial Index 156w (3 years)  — Williams method
# Panel 4: COT Commercial Index  52w (1 year)
# Panel 5: COT Commercial Index  26w (6 months)
# ─────────────────────────────────────────────────────────────

# (lookback weeks, label, line colour)
_INDEX_PANELS = [
    (156, "3-year / 156w — Williams method", _C_COMM),
    ( 52, "1-year  /  52w",                  "#7986cb"),   # indigo
    ( 26, "6-month /  26w",                  "#ffb74d"),   # amber
]


def _build_figure_b(df, snap, name, df_price, go, make_subplots, group: str = "comm"):
    """
    5-panel chart (Williams Figure 4.1 extended with shorter lookbacks).

    Panel 1 — Weekly price candlestick
    Panel 2 — Net position bar chart for `group` (green = net long, red = net short)
    Panel 3 — COT Index 156w  (3-year, Williams standard)
    Panel 4 — COT Index  52w  (1-year)
    Panel 5 — COT Index  26w  (6-month)
    All index panels share 20% / 80% reference lines.

    group : 'comm' | 'lrg' | 'sml'  (key into _GROUP_DEFS)
    """
    from cot_analyzer.utils.helpers import lw_index
    net_col, group_label, group_color = _GROUP_DEFS[group]

    n_idx = len(_INDEX_PANELS)   # 3
    fig = make_subplots(
        rows=2 + n_idx, cols=1,
        shared_xaxes=True,
        row_heights=[0.28, 0.12, 0.20, 0.20, 0.20],
        vertical_spacing=0.03,
        subplot_titles=[
            f"{name} — Weekly Price",
            f"COT {group_label} — Net Position  (long − short, contracts)",
        ] + [
            f"COT {group_label} Index  {lbl}" for _, lbl, _ in _INDEX_PANELS
        ],
    )

    cot_dates = df["date"].dt.strftime("%Y-%m-%d")

    # ── Panel 1: Candlestick ──────────────────────────────────
    has_price = df_price is not None and not df_price.empty
    req = {"date", "open", "high", "low", "close"}
    if has_price and req.issubset(df_price.columns):
        price_dates = df_price["date"].dt.strftime("%Y-%m-%d")
        fig.add_trace(go.Candlestick(
            x=price_dates,
            open=df_price["open"],
            high=df_price["high"],
            low=df_price["low"],
            close=df_price["close"],
            name="Price",
            increasing_line_color=_C_BULL,
            decreasing_line_color=_C_BEAR,
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_annotation(
            text="No price data — set 'ticker' in instruments.csv",
            xref="paper", yref="y1", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panel 2: Net position bar chart ──────────────────────
    if net_col in df.columns:
        net = df[net_col]
        bar_colors = [_C_BULL if v >= 0 else _C_BEAR for v in net]
        last_v = net.iloc[-1]
        fig.add_trace(go.Bar(
            x=cot_dates,
            y=net,
            name=f"{group_label} Net",
            marker_color=bar_colors,
            marker_line_width=0,
            opacity=0.85,
            hovertemplate=f"{group_label} Net: %{{y:,.0f}}<extra></extra>",
        ), row=2, col=1)
        _val_annotation(fig, cot_dates.iloc[-1], last_v,
                        f"{last_v/1000:.0f}K", group_color, 2, 1)

    fig.add_hline(
        y=0, row=2, col=1,
        line=dict(color="rgba(255,255,255,0.5)", width=1.2),
    )

    # ── Panels 3-5: COT Index (multiple lookbacks) ───────────
    if net_col in df.columns:
        for panel_row, (lb, lbl, color) in enumerate(_INDEX_PANELS, start=3):
            idx = lw_index(df[net_col], lb)
            last_v = idx.iloc[-1]

            # Compute fill colour from the line colour (15% opacity)
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            fill_c = f"rgba({r},{g},{b},0.13)"

            fig.add_trace(go.Scatter(
                x=cot_dates,
                y=idx,
                name=f"Index {lb}w",
                line=dict(color=color, width=1.8),
                fill="tozeroy",
                fillcolor=fill_c,
                hovertemplate=f"COT Index {lb}w: %{{y:.1f}}%<extra></extra>",
            ), row=panel_row, col=1)
            _val_annotation(fig, cot_dates.iloc[-1], last_v,
                            f"{last_v:.1f}%", color, panel_row, 1)

            # 80% / 20% / 50% reference lines on every index panel
            for level, label, ref_color, alpha in (
                (80, "80%", _C_BULL,  0.55),
                (20, "20%", _C_BEAR,  0.55),
                (50, "",    "#888888", 0.20),
            ):
                fig.add_hline(
                    y=level, row=panel_row, col=1,
                    line=dict(
                        color=f"rgba(255,255,255,{alpha})" if level == 50 else ref_color,
                        width=1.0, dash="dash",
                    ),
                    annotation_text=label if panel_row == 3 else "",
                    annotation_position="right",
                    annotation_font=dict(size=9,
                                        color=ref_color if level != 50 else "#666666"),
                )

    # ── Layout ───────────────────────────────────────────────
    date  = snap.get("date", "")
    state = snap.get("_market_state", "")
    fig.update_layout(
        title=dict(
            text=f"Figure B  ·  {name}  ·  {group_label}  ·  {date}  ·  {state}  "
                 "·  COT Index — 156w / 52w / 26w comparison",
            font=dict(size=13, color="#cccccc"), x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=1200,
        width=1400,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=100, t=70, b=50),
        bargap=0.1,
    )

    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    for r in range(1, 2 + n_idx):   # hide all but last panel
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.update_xaxes(showticklabels=True, row=2 + n_idx, col=1)

    gc = "rgba(255,255,255,0.05)"
    fig.update_yaxes(title_text="Price",      row=1, col=1, gridcolor=gc)
    fig.update_yaxes(title_text="Contracts",  row=2, col=1, gridcolor=gc)
    for r in range(3, 3 + n_idx):
        fig.update_yaxes(title_text="Index %", row=r, col=1,
                         range=[-5, 105], gridcolor=gc)

    fig.add_annotation(
        text=f"P2: {group_label} net — green = net long, red = net short  ·  "
             f"P3–P5: COT {group_label} Index at 3 lookback windows  ·  "
             "above 80% = bullish, below 20% = bearish  "
             "(Larry Williams, 'Trade Stocks & Commodities with the Insiders')",
        xref="paper", yref="paper", x=0.01, y=-0.04,
        showarrow=False, font=dict(color="#666666", size=9), align="left",
    )

    return fig


# ─────────────────────────────────────────────────────────────
# FIGURE C  (price + OI stochastic panels)
# Panel 1: weekly price candlestick
# Panel 2: lw_index(open_interest, 52) — stochastic 0-100%
#          secondary y: raw open interest (contracts)
# Panel 3: OI stochastic + Commercial NET (dotted, secondary y)
#          question: weak hands or strong hands driving the change?
# Panel 4: OI stochastic + Commercial LONGS (dotted, secondary y)
#          question: are Commercials actually buying (adding longs)?
# ─────────────────────────────────────────────────────────────

_OI_STOCH_LB = 52   # 1 year


def _build_figure_c(df, snap, name, df_price, go, make_subplots):
    """
    4-panel chart: price · OI stochastic · vs Comm Net · vs Comm Longs.

    Panel 1 — Weekly price candlestick
    Panel 2 — 52w OI stochastic (0-100%)  +  raw OI on secondary y
    Panel 3 — 52w OI stochastic  +  Commercial NET (long−short, secondary y)
               "Is OI expansion driven by strong or weak hands?"
    Panel 4 — 52w OI stochastic  +  Commercial LONGS (raw contracts, secondary y)
               "Are Commercials actively buying (adding longs) into rising OI?"
    """
    from cot_analyzer.utils.helpers import lw_index

    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        row_heights=[0.16, 0.21, 0.21, 0.21, 0.21],
        vertical_spacing=0.03,
        specs=[
            [{}],
            [{"secondary_y": True}],
            [{"secondary_y": True}],
            [{"secondary_y": True}],
            [{"secondary_y": True}],
        ],
        subplot_titles=[
            f"{name} — Weekly Price",
            f"Open Interest Stochastic  ({_OI_STOCH_LB}w / 1-year lookback)",
            "OI Stochastic  vs  Commercial Net  (long − short)  — who drives the change?",
            "OI Stochastic  vs  Commercial Longs  — are strong hands buying?",
            "OI Stochastic  vs  Commercial Shorts  — are strong hands selling / hedging?",
        ],
    )

    cot_dates = df["date"].dt.strftime("%Y-%m-%d")

    # ── Panel 1: Candlestick ──────────────────────────────────
    has_price = df_price is not None and not df_price.empty
    req = {"date", "open", "high", "low", "close"}
    if has_price and req.issubset(df_price.columns):
        price_dates = df_price["date"].dt.strftime("%Y-%m-%d")
        fig.add_trace(go.Candlestick(
            x=price_dates,
            open=df_price["open"],
            high=df_price["high"],
            low=df_price["low"],
            close=df_price["close"],
            name="Price",
            increasing_line_color=_C_BULL,
            decreasing_line_color=_C_BEAR,
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_annotation(
            text="No price data — set 'ticker' in instruments.csv",
            xref="paper", yref="y1", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Compute OI stochastic once, reused in all panels ─────
    has_oi = "open_interest" in df.columns
    if has_oi:
        oi    = df["open_interest"].replace(0, float("nan"))
        stoch = lw_index(oi, _OI_STOCH_LB)
        last_stoch = stoch.iloc[-1]
        r, g, b = int(_C_OI[1:3], 16), int(_C_OI[3:5], 16), int(_C_OI[5:7], 16)
        fill_c = f"rgba({r},{g},{b},0.18)"

    def _add_ref_lines(row: int, annotate: bool):
        """80 / 20 / 50 dashed reference lines on the OI stochastic axis."""
        for level, label, ref_color, alpha in (
            (80, "80%", _C_BULL,  0.55),
            (20, "20%", _C_BEAR,  0.55),
            (50, "",    "#888888", 0.20),
        ):
            fig.add_hline(
                y=level, row=row, col=1,
                line=dict(
                    color=f"rgba(255,255,255,{alpha})" if level == 50 else ref_color,
                    width=1.0, dash="dash",
                ),
                annotation_text=label if annotate else "",
                annotation_position="right",
                annotation_font=dict(size=9,
                                     color=ref_color if level != 50 else "#666666"),
            )

    def _add_stoch_line(row: int):
        """OI stochastic line (no fill) for overlay panels."""
        fig.add_trace(go.Scatter(
            x=cot_dates, y=stoch,
            name=f"OI Stochastic ({_OI_STOCH_LB}w)",
            line=dict(color=_C_OI, width=2.0),
            showlegend=(row == 2),   # show in legend only once
            hovertemplate="OI Stoch: %{y:.1f}%<extra></extra>",
        ), row=row, col=1, secondary_y=False)
        _val_annotation(fig, cot_dates.iloc[-1], last_stoch,
                        f"{last_stoch:.1f}%", _C_OI, row, 1)

    # ── Panel 2: filled stochastic + raw OI (secondary y) ────
    if has_oi:
        fig.add_trace(go.Scatter(
            x=cot_dates, y=stoch,
            name=f"OI Stochastic ({_OI_STOCH_LB}w)",
            line=dict(color=_C_OI, width=2.0),
            fill="tozeroy",
            fillcolor=fill_c,
            hovertemplate="OI Stoch: %{y:.1f}%<extra></extra>",
        ), row=2, col=1, secondary_y=False)
        _val_annotation(fig, cot_dates.iloc[-1], last_stoch,
                        f"{last_stoch:.1f}%", _C_OI, 2, 1)

        fig.add_trace(go.Scatter(
            x=cot_dates, y=oi,
            name="Open Interest (raw)",
            line=dict(color=_C_OI, width=1.0, dash="dot"),
            opacity=0.35,
            hovertemplate="OI: %{y:,.0f}<extra></extra>",
        ), row=2, col=1, secondary_y=True)

        _add_ref_lines(row=2, annotate=True)
    else:
        fig.add_annotation(
            text="No Open Interest data available",
            xref="paper", yref="paper", x=0.5, y=0.68,
            showarrow=False, font=dict(color="#aaaaaa", size=13),
        )

    # ── Panel 3: OI stochastic + Commercial NET ───────────────
    if has_oi:
        _add_stoch_line(row=3)
        _add_ref_lines(row=3, annotate=False)

    if "comm_net" in df.columns:
        comm_net  = df["comm_net"]
        last_net  = comm_net.iloc[-1]
        fig.add_trace(go.Scatter(
            x=cot_dates, y=comm_net,
            name="Commercial Net — strong hands",
            line=dict(color=_C_COMM, width=1.8, dash="dot"),
            hovertemplate="Comm Net: %{y:,.0f}<extra></extra>",
        ), row=3, col=1, secondary_y=True)
        _val_annotation(fig, cot_dates.iloc[-1], last_net,
                        f"{last_net/1000:.0f}K", _C_COMM, 3, 1)
        # faint zero line for the net position
        fig.add_hline(
            y=0, row=3, col=1,
            line=dict(color="rgba(38,166,154,0.30)", width=1.0, dash="dash"),
        )
    elif has_oi:
        fig.add_annotation(
            text="comm_net not available",
            xref="paper", yref="paper", x=0.5, y=0.42,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panel 4: OI stochastic + Commercial LONGS ────────────
    if has_oi:
        _add_stoch_line(row=4)
        _add_ref_lines(row=4, annotate=False)

    if "comm_long" in df.columns:
        comm_long  = df["comm_long"]
        last_long  = comm_long.iloc[-1]
        fig.add_trace(go.Scatter(
            x=cot_dates, y=comm_long,
            name="Commercial Longs (gross)",
            line=dict(color=_C_COMM, width=1.8, dash="dot"),
            hovertemplate="Comm Longs: %{y:,.0f}<extra></extra>",
        ), row=4, col=1, secondary_y=True)
        _val_annotation(fig, cot_dates.iloc[-1], last_long,
                        f"{last_long/1000:.0f}K", _C_COMM, 4, 1)
    elif has_oi:
        fig.add_annotation(
            text="comm_long not available",
            xref="paper", yref="paper", x=0.5, y=0.15,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panel 5: OI stochastic + Commercial SHORTS ────────────
    if has_oi:
        _add_stoch_line(row=5)
        _add_ref_lines(row=5, annotate=False)

    if "comm_short" in df.columns:
        comm_short = df["comm_short"]
        last_short = comm_short.iloc[-1]
        fig.add_trace(go.Scatter(
            x=cot_dates, y=comm_short,
            name="Commercial Shorts (gross)",
            line=dict(color=_C_BEAR, width=1.8, dash="dot"),
            hovertemplate="Comm Shorts: %{y:,.0f}<extra></extra>",
        ), row=5, col=1, secondary_y=True)
        _val_annotation(fig, cot_dates.iloc[-1], last_short,
                        f"{last_short/1000:.0f}K", _C_BEAR, 5, 1)
    elif has_oi:
        fig.add_annotation(
            text="comm_short not available",
            xref="paper", yref="paper", x=0.5, y=0.02,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Layout ───────────────────────────────────────────────
    date  = snap.get("date", "")
    state = snap.get("_market_state", "")
    fig.update_layout(
        title=dict(
            text=f"Figure C  ·  {name}  ·  {date}  ·  {state}  "
                 f"·  OI Stochastic ({_OI_STOCH_LB}w) + Commercial Positioning",
            font=dict(size=13, color="#cccccc"), x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=1500,
        width=1400,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=100, t=70, b=65),
    )

    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    for r in (1, 2, 3, 4):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.update_xaxes(showticklabels=True, row=5, col=1)

    gc = "rgba(255,255,255,0.05)"
    fig.update_yaxes(title_text="Price",         row=1, col=1, gridcolor=gc)
    fig.update_yaxes(title_text="OI Stoch %",    row=2, col=1,
                     secondary_y=False, range=[-5, 105], gridcolor=gc)
    fig.update_yaxes(title_text="Open Interest", row=2, col=1,
                     secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="OI Stoch %",    row=3, col=1,
                     secondary_y=False, range=[-5, 105], gridcolor=gc)
    fig.update_yaxes(title_text="Comm Net",      row=3, col=1,
                     secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="OI Stoch %",    row=4, col=1,
                     secondary_y=False, range=[-5, 105], gridcolor=gc)
    fig.update_yaxes(title_text="Comm Longs",    row=4, col=1,
                     secondary_y=True, showgrid=False)
    fig.update_yaxes(title_text="OI Stoch %",    row=5, col=1,
                     secondary_y=False, range=[-5, 105], gridcolor=gc)
    fig.update_yaxes(title_text="Comm Shorts",   row=5, col=1,
                     secondary_y=True, showgrid=False)

    fig.add_annotation(
        text=f"P2: OI Stochastic = (OI − min_{_OI_STOCH_LB}w) / (max_{_OI_STOCH_LB}w − min_{_OI_STOCH_LB}w) × 100  ·  "
             "P3: vs Comm NET (long−short) — rising OI + rising net = strong hands driving expansion  ·  "
             "P4: vs Comm LONGS — are Commercials buying?  ·  "
             "P5: vs Comm SHORTS — are Commercials hedging/distributing?",
        xref="paper", yref="paper", x=0.01, y=-0.04,
        showarrow=False, font=dict(color="#666666", size=9), align="left",
    )

    return fig


# ─────────────────────────────────────────────────────────────
# FIGURE D  (WillCo: book formula vs our formula, side by side)
#
# Book  (Williams): comm_short / OI  — 26w stochastic
#   HIGH (>80%) = commercials heavily hedged  → BEARISH signal
#   LOW  (<20%) = commercials light on hedges → BULLISH signal
#
# Ours: comm_net / OI  — 26w stochastic
#   HIGH (>80%) = commercials strongly net long → BULLISH signal
#   LOW  (<20%) = commercials strongly net short→ BEARISH signal
#
# Note the directions are OPPOSITE — both panels show the same
# underlying reality, just from different angles.
# ─────────────────────────────────────────────────────────────

_WILLCO_LB = 26   # 6 months — Williams standard


def _build_figure_d(df, snap, name, df_price, go, make_subplots):
    """
    3-panel WillCo comparison chart.

    Panel 1 — Weekly price candlestick
    Panel 2 — WillCo Book : stoch(comm_short / OI, 26w)
               HIGH = bearish  (heavy producer hedging)
               LOW  = bullish  (light hedging → producers expect rising prices)
    Panel 3 — WillCo Ours : stoch(comm_net / OI, 26w)
               HIGH = bullish  (commercials strongly net long)
               LOW  = bearish  (commercials strongly net short)

    Divergence between the two reveals spreading activity:
    if P2 rises (shorts up) but P3 stays flat, commercials are adding
    both longs AND shorts simultaneously (spreading/hedging structure).
    """
    from cot_analyzer.utils.helpers import lw_index

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.28, 0.36, 0.36],
        vertical_spacing=0.04,
        specs=[[{}], [{}], [{}]],
        subplot_titles=[
            f"{name} — Weekly Price",
            f"WillCo (Book)  —  comm_short ÷ OI  ·  {_WILLCO_LB}w  "
            "·  HIGH = bearish  /  LOW = bullish",
            f"WillCo (Ours)  —  comm_net ÷ OI  ·  {_WILLCO_LB}w  "
            "·  HIGH = bullish  /  LOW = bearish",
        ],
    )

    cot_dates = df["date"].dt.strftime("%Y-%m-%d")

    # ── Panel 1: Candlestick ──────────────────────────────────
    has_price = df_price is not None and not df_price.empty
    req = {"date", "open", "high", "low", "close"}
    if has_price and req.issubset(df_price.columns):
        price_dates = df_price["date"].dt.strftime("%Y-%m-%d")
        fig.add_trace(go.Candlestick(
            x=price_dates,
            open=df_price["open"],
            high=df_price["high"],
            low=df_price["low"],
            close=df_price["close"],
            name="Price",
            increasing_line_color=_C_BULL,
            decreasing_line_color=_C_BEAR,
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_annotation(
            text="No price data — set 'ticker' in instruments.csv",
            xref="paper", yref="y1", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    oi = df["open_interest"].replace(0, float("nan")) if "open_interest" in df.columns else None

    def _add_willco_panel(row: int, series: pd.Series, label: str,
                          color: str, bull_at_high: bool):
        """Compute stoch(series/OI, LB) and plot on the given row."""
        if oi is None:
            fig.add_annotation(
                text="No open_interest column",
                xref="paper", yref="paper", x=0.5, y=0.5 - row * 0.3,
                showarrow=False, font=dict(color="#aaaaaa", size=11),
            )
            return

        raw   = series.div(oi)
        stoch = lw_index(raw, _WILLCO_LB)
        last  = stoch.iloc[-1]

        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        fill_c  = f"rgba({r},{g},{b},0.15)"

        fig.add_trace(go.Scatter(
            x=cot_dates, y=stoch,
            name=label,
            line=dict(color=color, width=2.0),
            fill="tozeroy",
            fillcolor=fill_c,
            hovertemplate=f"{label}: %{{y:.1f}}%<extra></extra>",
        ), row=row, col=1)
        _val_annotation(fig, cot_dates.iloc[-1], last, f"{last:.1f}%", color, row, 1)

        # Reference lines — 80/20 colors follow interpretation direction
        bull_color = _C_BULL if bull_at_high else _C_BEAR
        bear_color = _C_BEAR if bull_at_high else _C_BULL
        for level, lbl, lcolor, alpha in (
            (80, "80%", bull_color, 0.55),
            (20, "20%", bear_color, 0.55),
            (50, "",    "#888888",  0.20),
        ):
            fig.add_hline(
                y=level, row=row, col=1,
                line=dict(
                    color=f"rgba(255,255,255,{alpha})" if level == 50 else lcolor,
                    width=1.0, dash="dash",
                ),
                annotation_text=lbl,
                annotation_position="right",
                annotation_font=dict(size=9,
                                     color=lcolor if level != 50 else "#666666"),
            )

    # ── Panel 2: Book formula (comm_short / OI) ───────────────
    if "comm_short" in df.columns:
        _add_willco_panel(
            row=2,
            series=df["comm_short"],
            label=f"WillCo Book ({_WILLCO_LB}w) — comm_short÷OI",
            color=_C_BEAR,       # red fill — high = bearish
            bull_at_high=False,
        )
    else:
        fig.add_annotation(
            text="comm_short not available",
            xref="paper", yref="paper", x=0.5, y=0.58,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panel 3: Our formula (comm_net / OI) ──────────────────
    if "comm_net" in df.columns:
        _add_willco_panel(
            row=3,
            series=df["comm_net"],
            label=f"WillCo Ours ({_WILLCO_LB}w) — comm_net÷OI",
            color=_C_COMM,       # teal fill — high = bullish
            bull_at_high=True,
        )
    else:
        fig.add_annotation(
            text="comm_net not available",
            xref="paper", yref="paper", x=0.5, y=0.22,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Layout ───────────────────────────────────────────────
    date  = snap.get("date", "")
    state = snap.get("_market_state", "")
    fig.update_layout(
        title=dict(
            text=f"Figure D  ·  {name}  ·  {date}  ·  {state}  "
                 f"·  WillCo comparison ({_WILLCO_LB}w)  ·  Book vs Ours",
            font=dict(size=13, color="#cccccc"), x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=1000,
        width=1400,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.01, xanchor="left", x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=60, r=100, t=70, b=70),
    )

    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    for r in (1, 2):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    fig.update_xaxes(showticklabels=True, row=3, col=1)

    gc = "rgba(255,255,255,0.05)"
    fig.update_yaxes(title_text="Price",     row=1, col=1, gridcolor=gc)
    fig.update_yaxes(title_text="WillCo %",  row=2, col=1,
                     range=[-5, 105], gridcolor=gc)
    fig.update_yaxes(title_text="WillCo %",  row=3, col=1,
                     range=[-5, 105], gridcolor=gc)

    fig.add_annotation(
        text=f"Both panels: stochastic = (raw − min_{_WILLCO_LB}w) / (max_{_WILLCO_LB}w − min_{_WILLCO_LB}w) × 100  ·  "
             "Book (P2, red): raw = comm_short÷OI — HIGH means heavy hedging = bearish  ·  "
             "Ours (P3, teal): raw = comm_net÷OI  — HIGH means net long = bullish  ·  "
             "Divergence = commercials spreading (adding both longs & shorts simultaneously)",
        xref="paper", yref="paper", x=0.01, y=-0.06,
        showarrow=False, font=dict(color="#666666", size=9), align="left",
    )

    return fig


# ─────────────────────────────────────────────────────────────
# FIGURE E  (price + 3 multi-period COT tables)
#
# Each table: rows = 1M / 3M / 6M / 1Y / 3Y
#             cols = Timeframe | Commercial % | Non-Comm % | Small Spec % | Open Int %
#
# Table 1 — LW Index    : lw_index(net, N)           always 0–100%
# Table 2 — Percentile  : (net − min_N[t-1]) / range  unclamped, can exceed 0–100%
# Table 3 — WillCo      : lw_index(net / OI, N)       OI-adjusted, 0–100%
#
# 3Y row always highlighted.
# ─────────────────────────────────────────────────────────────

_PERIODS_DEF = [
    ("1 Month",  4),
    ("3 Months", 13),
    ("6 Months", 26),
    ("1 Year",   52),
    ("3 Years",  156),
]
_3Y_ROW_IDX = 4          # 0-based index of the 3Y row in _PERIODS_DEF
_3Y_BG      = "#2d3252"  # highlighted background for 3Y row


def _table_cell_color(v: float) -> str:
    """Font colour based on percentage value. Handles Percentile outside 0–100."""
    if pd.isna(v):   return "#888888"
    if v > 100:      return "#00e676"   # Percentile breakout above → extra bright green
    if v >= 75:      return _C_BULL
    if v < 0:        return "#ff5252"   # Percentile breakout below → extra bright red
    if v <= 25:      return _C_BEAR
    return "#cccccc"


def _table_fmt(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.1f}%"


def _compute_fig_e_table(df: pd.DataFrame, method: str, go) -> "go.Table":
    """
    Build one Plotly Table trace for Figure E.

    method : 'LW_Index' | 'Percentile' | 'WillCo'
    """
    from cot_analyzer.utils.helpers import lw_index

    oi = (df["open_interest"].replace(0, float("nan"))
          if "open_interest" in df.columns else None)

    period_col: list[str]   = []
    comm_vals:  list[float] = []
    lrg_vals:   list[float] = []
    sml_vals:   list[float] = []
    oi_vals:    list[float] = []

    for label, weeks in _PERIODS_DEF:
        period_col.append(label)

        for result_list, col_name in (
            (comm_vals, "comm_net"),
            (lrg_vals,  "lrg_net"),
            (sml_vals,  "sml_net"),
        ):
            if col_name not in df.columns:
                result_list.append(float("nan"))
                continue

            s = df[col_name]

            if method == "LW_Index":
                val = lw_index(s, weeks).iloc[-1]

            elif method == "Percentile":
                # Unclamped — may exceed 0–100 at extremes
                shifted = s.shift(1)
                rmin    = shifted.rolling(weeks, min_periods=weeks).min()
                rmax    = shifted.rolling(weeks, min_periods=weeks).max()
                rng     = (rmax - rmin).replace(0, float("nan"))
                val     = ((s - rmin) / rng * 100).fillna(50.0).iloc[-1]

            else:  # WillCo
                val = (lw_index(s.div(oi), weeks).iloc[-1]
                       if oi is not None else float("nan"))

            result_list.append(val)

        # OI column — LW stochastic of raw open interest
        oi_vals.append(
            lw_index(oi, weeks).iloc[-1] if oi is not None else float("nan")
        )

    # ── Build Plotly table ────────────────────────────────────
    n = len(_PERIODS_DEF)

    def _bg_col():
        return [_3Y_BG if i == _3Y_ROW_IDX else _PANEL for i in range(n)]

    return go.Table(
        columnwidth=[60, 65, 60, 65, 60],
        header=dict(
            values=["Timeframe", "Commercial %", "Non-Comm %",
                    "Small Spec %", "Open Int %"],
            fill_color=_BG,
            font=dict(color="#aaaaaa", size=10),
            align="center",
            height=20,
        ),
        cells=dict(
            values=[
                period_col,
                [_table_fmt(v) for v in comm_vals],
                [_table_fmt(v) for v in lrg_vals],
                [_table_fmt(v) for v in sml_vals],
                [_table_fmt(v) for v in oi_vals],
            ],
            fill_color=[_bg_col() for _ in range(5)],
            font=dict(
                color=[
                    ["#aaaaaa"] * n,
                    [_table_cell_color(v) for v in comm_vals],
                    [_table_cell_color(v) for v in lrg_vals],
                    [_table_cell_color(v) for v in sml_vals],
                    [_table_cell_color(v) for v in oi_vals],
                ],
                size=11,
            ),
            align=["left"] + ["center"] * 4,
            height=24,
        ),
    )


def _build_figure_e(df, snap, name, df_price, go, make_subplots):
    """
    4-row figure: price candlestick + 3 COT tables (LW Index / Percentile / WillCo).

    Each table has rows 1M / 3M / 6M / 1Y / 3Y and columns for all three
    trader groups plus Open Interest.  The 3Y row is always highlighted.
    """
    fig = make_subplots(
        rows=4, cols=1,
        row_heights=[0.30, 0.23, 0.23, 0.24],
        vertical_spacing=0.05,
        specs=[
            [{}],
            [{"type": "table"}],
            [{"type": "table"}],
            [{"type": "table"}],
        ],
        subplot_titles=[
            f"{name} — Weekly Price",
            "LW Index  —  min-max of raw net position  (always 0–100%)",
            "Percentile  —  excludes current bar  (can go below 0% or above 100%)",
            "WillCo  —  min-max of net ÷ OI, OI-adjusted  (always 0–100%)",
        ],
    )

    # ── Panel 1: Candlestick ──────────────────────────────────
    has_price = df_price is not None and not df_price.empty
    req = {"date", "open", "high", "low", "close"}
    if has_price and req.issubset(df_price.columns):
        price_dates = df_price["date"].dt.strftime("%Y-%m-%d")
        fig.add_trace(go.Candlestick(
            x=price_dates,
            open=df_price["open"],
            high=df_price["high"],
            low=df_price["low"],
            close=df_price["close"],
            name="Price",
            increasing_line_color=_C_BULL,
            decreasing_line_color=_C_BEAR,
            showlegend=False,
        ), row=1, col=1)
    else:
        fig.add_annotation(
            text="No price data — set 'ticker' in instruments.csv",
            xref="paper", yref="y1", x=0.5, y=0.5,
            showarrow=False, font=dict(color="#aaaaaa", size=11),
        )

    # ── Panels 2–4: one table per method ─────────────────────
    for row, method in ((2, "LW_Index"), (3, "Percentile"), (4, "WillCo")):
        fig.add_trace(_compute_fig_e_table(df, method, go), row=row, col=1)

    # ── Layout ───────────────────────────────────────────────
    date  = snap.get("date", "")
    state = snap.get("_market_state", "")
    fig.update_layout(
        title=dict(
            text=f"Figure E  ·  {name}  ·  {date}  ·  {state}  "
                 "·  Multi-period COT table  ·  3Y row highlighted",
            font=dict(size=13, color="#cccccc"), x=0.01,
        ),
        template="plotly_dark",
        paper_bgcolor=_BG,
        plot_bgcolor=_PANEL,
        hovermode="x unified",
        height=1050,
        width=1400,
        showlegend=False,
        margin=dict(l=60, r=40, t=70, b=55),
    )

    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1,
                     gridcolor="rgba(255,255,255,0.05)")

    fig.add_annotation(
        text="Color: teal ≥75%  ·  red ≤25%  ·  bright green >100% / bright red <0% (Percentile only)  ·  "
             "3Y row highlighted — Williams' recommended lookback  ·  "
             "LW & WillCo always 0–100%  ·  Percentile unclamped: extremes break the range",
        xref="paper", yref="paper", x=0.01, y=-0.03,
        showarrow=False, font=dict(color="#666666", size=9), align="left",
    )

    return fig


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def save_chart(
    df: pd.DataFrame,
    snap: dict,
    instrument_name: str,
    output_folder: Path,
    primary_lb: int,
    secondary_lb: int,
    heavy_buyers: int,
    heavy_sellers: int,
    chart_type: str = "COT_Index",
    chart_format: str = "html",
    analysis_method: str = "LW_Index",
    historical: dict | None = None,
    proximity_lb: int = 13,
    df_price: pd.DataFrame | None = None,
) -> list[Path]:
    """
    Generate and save chart(s) for one instrument.

    chart_type   : 'COT_Report' | 'COT_Index' | 'COT_Proximity' | 'Figure_A' | 'All'
    chart_format : 'png' | 'html' | 'both'

    Returns list of saved Path objects.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("plotly is required. Install with: pip install plotly")

    charts_dir = output_folder / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    safe = _sanitize(instrument_name)
    historical = historical or {}
    saved: list[Path] = []

    modes = (
        ["COT_Report", "COT_Index", "COT_Proximity", "Figure_A", "Figure_B_Groups", "Figure_C", "Figure_D", "Figure_E"]
        if chart_type == "All" else [chart_type]
    )

    for mode in modes:
        slug = mode.lower()

        if mode == "COT_Report":
            fig = _build_cot_report(
                df, snap, instrument_name, go, make_subplots,
                historical, heavy_buyers, heavy_sellers,
            )

        elif mode == "COT_Index":
            fig = _build_cot_index(
                df, snap, instrument_name, go, make_subplots,
                historical, heavy_buyers, heavy_sellers,
                primary_lb, secondary_lb, analysis_method,
            )

        elif mode == "COT_Proximity":
            fig = _build_cot_proximity(
                df, snap, instrument_name, go, make_subplots,
                historical, heavy_buyers, heavy_sellers,
                proximity_lb,
            )

        elif mode == "Figure_A":
            fig = _build_figure_a(
                df, snap, instrument_name, df_price, go, make_subplots,
                heavy_buyers, heavy_sellers,
            )

        elif mode == "Figure_C":
            fig = _build_figure_c(
                df, snap, instrument_name, df_price, go, make_subplots,
            )

        elif mode == "Figure_D":
            fig = _build_figure_d(
                df, snap, instrument_name, df_price, go, make_subplots,
            )

        elif mode == "Figure_E":
            fig = _build_figure_e(
                df, snap, instrument_name, df_price, go, make_subplots,
            )

        elif mode == "Figure_B_Groups":
            # Generate one file per trader group
            for grp in _GROUP_DEFS:
                fig_g = _build_figure_b(
                    df, snap, instrument_name, df_price, go, make_subplots, group=grp,
                )
                slug_g = f"figure_b_{grp}"
                if chart_format in ("html", "both"):
                    out_path = charts_dir / f"{safe}_{slug_g}.html"
                    fig_g.write_html(str(out_path), include_plotlyjs="cdn")
                    saved.append(out_path)
                if chart_format in ("png", "both"):
                    out_path = charts_dir / f"{safe}_{slug_g}.png"
                    try:
                        fig_g.write_image(str(out_path), width=1400, height=1200, scale=2)
                    except Exception as exc:
                        raise RuntimeError(
                            f"PNG export failed: {exc}. "
                            "Install kaleido: pip install kaleido"
                        ) from exc
                    saved.append(out_path)
            continue   # skip the generic export block below

        else:  # Figure_B
            fig = _build_figure_b(
                df, snap, instrument_name, df_price, go, make_subplots,
            )

        # Export according to chart_format
        if chart_format in ("html", "both"):
            out_path = charts_dir / f"{safe}_{slug}.html"
            fig.write_html(str(out_path), include_plotlyjs="cdn")
            saved.append(out_path)

        if chart_format in ("png", "both"):
            out_path = charts_dir / f"{safe}_{slug}.png"
            # Tall multi-panel figures need extra height
            if mode == "Figure_A":
                png_height = 1300
            elif mode in ("Figure_B", "Figure_B_Groups"):
                png_height = 1200
            elif mode == "Figure_C":
                png_height = 1500
            elif mode == "Figure_D":
                png_height = 1000
            elif mode == "Figure_E":
                png_height = 1050
            else:
                png_height = 900
            try:
                fig.write_image(str(out_path), width=1400, height=png_height, scale=2)
            except Exception as exc:
                raise RuntimeError(
                    f"PNG export failed: {exc}. "
                    "Install kaleido: pip install kaleido"
                ) from exc
            saved.append(out_path)

    return saved
