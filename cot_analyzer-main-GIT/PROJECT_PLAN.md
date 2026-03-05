# COT Analyzer — Python Project Plan
## Larry Williams Methodology — Independent of TradingView

**Date:** 2026-03-03
**Reference indicator:** tradeviZion Larry Williams COT Analysis Enhanced
**Methodology source:** v5_methodology.md, cot_interpretation_guide.md, tradevizion_reference.md

---

## 1. Project Goal

Build a standalone Python application that:
1. **Automatically downloads** the latest COT report from CFTC every week
2. **Calculates** WillCo Index, Standard COT Index, Percentile, Market State, and signals
3. **Displays** an interactive dashboard modeled after the tradeviZion indicator structure
4. **Requires no TradingView** — fully self-contained, runs locally

---

## 2. Data Source — CFTC Direct Download

### Official CFTC URLs

| Report Type | URL Pattern | Available Since |
|---|---|---|
| Legacy Futures-Only (annual ZIP) | `https://www.cftc.gov/files/dea/history/fut_disagg_txt_{YEAR}.zip` | 1986 |
| Legacy Futures-Only (current year) | `https://www.cftc.gov/files/dea/history/deahistfo_2016_2025.zip` | — |
| Legacy current weekly | `https://www.cftc.gov/dea/futures/deacmesf.htm` (HTML) | — |
| Disaggregated Futures-Only | `https://www.cftc.gov/files/dea/history/fut_disagg_txt_{YEAR}.zip` | 2009 |
| TFF (Financial) Futures-Only | `https://www.cftc.gov/files/dea/history/fut_fin_txt_{YEAR}.zip` | 2009 |

### Primary Python Library: `cot-reports`

```bash
pip install cot-reports
```

**GitHub:** https://github.com/NDelventhal/cot_reports

**Supported report types:**
- `legacy_fut`          — Legacy Futures-only ✅ (our primary)
- `legacy_futopt`       — Legacy Futures + Options
- `supplemental_futopt` — Supplemental Futures + Options
- `disaggregated_fut`   — Disaggregated Futures-only ✅
- `disaggregated_futopt`— Disaggregated Futures + Options
- `traders_in_fin_fut_fut`    — TFF Futures-only ✅
- `traders_in_fin_fut_futopt` — TFF Futures + Options

**Key functions:**
```python
import cot_reports as cot

# Fetch historical (bulk, from 1986 to 2016)
df = cot.cot_hist(cot_report_type='legacy_fut')

# Fetch year by year
df = cot.cot_year(year=2025, cot_report_type='legacy_fut')

# Fetch all data up to current
df = cot.cot_all(cot_report_type='legacy_fut')
```

Returns a pandas DataFrame — one row per instrument per week.

### Alternative: `pycot-reports`
```bash
pip install pycot-reports
```
GitHub: https://github.com/philsv/pycot
Simpler API, fewer report types.

### Fallback: Direct CFTC Download
Direct ZIP download from CFTC if library fails:
```
https://www.cftc.gov/files/dea/history/fut_disagg_txt_{YEAR}.zip
```
Unzip → parse CSV with pandas.

### Update Schedule
- CFTC publishes every **Friday at 3:30 PM ET**
- Data reports **Tuesday positions** (3-day lag)
- App should auto-check and update on Fridays

---

## 3. CFTC Legacy CSV Column Names

Key columns in the Legacy Futures-Only report:

| Column | Description |
|---|---|
| `Market_and_Exchange_Names` | Instrument name (e.g. "GOLD - COMMODITY EXCHANGE INC.") |
| `CFTC_Market_Code` | CFTC code (e.g. "088691") |
| `As_of_Date_In_Form_YYMMDD` | Report date |
| `Open_Interest_All` | Total open interest |
| `Comm_Positions_Long_All` | Commercial long contracts |
| `Comm_Positions_Short_All` | Commercial short contracts |
| `NonComm_Positions_Long_All` | Large spec long |
| `NonComm_Positions_Short_All` | Large spec short |
| `NonComm_Positions_Spreading_All` | Large spec spread positions |
| `NonRept_Positions_Long_All` | Small spec long |
| `NonRept_Positions_Short_All` | Small spec short |
| `Change_in_Open_Interest_All` | Week-over-week OI change |
| `Change_in_Comm_Long_All` | Week-over-week commercial long change |
| `Change_in_Comm_Short_All` | Week-over-week commercial short change |
| `Change_in_NonComm_Long_All` | Week-over-week large spec long change |
| `Change_in_NonComm_Short_All` | Week-over-week large spec short change |
| `Change_in_NonRept_Long_All` | Week-over-week small spec long change |
| `Change_in_NonRept_Short_All` | Week-over-week small spec short change |
| `Pct_of_OI_Comm_Long_All` | Commercial long as % of OI |
| `Pct_of_OI_Comm_Short_All` | Commercial short as % of OI |
| `Traders_Comm_Long_All` | Number of commercial long traders |
| `Traders_Comm_Short_All` | Number of commercial short traders |
| `Conc_Gross_LE_4_TDR_Long_All` | Top 4 traders long concentration % |
| `Conc_Gross_LE_4_TDR_Short_All` | Top 4 traders short concentration % |
| `Conc_Gross_LE_8_TDR_Long_All` | Top 8 traders long concentration % |
| `Conc_Gross_LE_8_TDR_Short_All` | Top 8 traders short concentration % |

---

## 4. Instrument Mapping (CFTC Codes)

Same as v5 Pine Script, confirmed from CFTC:

```python
INSTRUMENTS = {
    # Metals
    "GC - Gold":         {"code": "088691", "lookback": 13, "type": "Metal"},
    "MGC - Micro Gold":  {"code": "088695", "lookback": 13, "type": "Metal"},
    "SI - Silver":       {"code": "084691", "lookback": 13, "type": "Metal"},
    "HG - Copper":       {"code": "085692", "lookback": 13, "type": "Metal"},
    "PL - Platinum":     {"code": "076651", "lookback": 13, "type": "Metal"},
    "PA - Palladium":    {"code": "075651", "lookback": 13, "type": "Metal"},
    "ALI - Aluminum":    {"code": "191651", "lookback": 13, "type": "Metal"},
    # Energy
    "CL - Crude Oil":    {"code": "067651", "lookback": 13, "type": "Energy"},
    "NG - Natural Gas":  {"code": "023651", "lookback": 13, "type": "Energy"},
    # Indices
    "NQ - Nasdaq":       {"code": "209742", "lookback": 13, "type": "Index"},
    "ES - S&P 500":      {"code": "13874A", "lookback": 13, "type": "Index"},
    "YM - Dow":          {"code": "124606", "lookback": 13, "type": "Index"},
    "RTY - Russell":     {"code": "239742", "lookback": 13, "type": "Index"},
    # Bonds
    "ZB - T-Bond 30Y":   {"code": "020601", "lookback": 52, "type": "Bond"},
    "ZN - T-Note 10Y":   {"code": "043602", "lookback": 52, "type": "Bond"},
    # FX
    "6E - Euro":         {"code": "099741", "lookback": 26, "type": "FX"},
    "6J - Yen":          {"code": "097741", "lookback": 26, "type": "FX"},
    "6B - GBP":          {"code": "096742", "lookback": 26, "type": "FX"},
    "6A - AUD":          {"code": "232741", "lookback": 26, "type": "FX"},
    # Crypto
    "BTC - Bitcoin":     {"code": "133741", "lookback": 26, "type": "Crypto"},
}
```

---

## 5. Calculations to Implement

Modeled directly on tradeviZion's analysis structure:

### 5.1 Net Positions
```
comm_net  = comm_long  - comm_short
lrg_net   = lrg_long   - lrg_short
sml_net   = sml_long   - sml_short
```

### 5.2 WillCo Index (Larry Williams primary — OI-adjusted)
```
willco_raw   = (comm_net / open_interest) * 100
willco_index = (willco_raw - min(willco_raw, N)) / (max(willco_raw, N) - min(willco_raw, N)) * 100
```

### 5.3 Standard LW Index (0–100%, inclusive of current bar)
```
lw_index = (net - min(net, N)) / (max(net, N) - min(net, N)) * 100
```

### 5.4 Percentile Method (excludes current bar — tradeviZion default)
```
percentile = (net - min(net[1:], N)) / (max(net[1:], N) - min(net[1:], N)) * 100
# Can exceed 0–100% when current value breaks historical range
```

### 5.5 Smoothing
```python
def smooth(series, method, period):
    if method == "SMA": return series.rolling(period).mean()
    if method == "EMA": return series.ewm(span=period).mean()
    if method == "WMA": return series.apply(lambda x: weighted_average(x, period))
    if method == "RMA": return series.ewm(alpha=1/period).mean()  # Wilder's
    return series  # None
```

### 5.6 Market State (tradeviZion logic)
Score-based system:
```
+2 if commercial WillCo > heavy_buyers (74%)
+1 if commercial WillCo > 60%
-1 if lrg_spec WillCo  > 70%  (contrarian)
+1 if sml_spec WillCo  < 30%  (contrarian)
+1 if OI rising and comm driving
-1 if OI rising and specs driving

Score → State:
  ≥ 3   = STRONG BULLISH
  2     = MODERATE BULLISH
  1     = LEANING BULLISH
  0     = NEUTRAL
  -1    = LEANING BEARISH
  -2    = MODERATE BEARISH
  ≤ -3  = STRONG BEARISH
```

### 5.7 Signal Combination Detection
```
bull_conf     = willco_comm > 90 AND willco_lrg < 10
bear_conf     = willco_comm < 10 AND willco_lrg > 90
comm_spec_oi  = bull_conf AND oi_rising_comm_driven
comm_only     = willco_comm > heavy_buyers
```

### 5.8 Historical Percentile Ranks
For each group, compute where current value ranks in: 1M, 3M, 6M, 1Y, 3Y, All-time

### 5.9 OI Analysis — Who is Driving Changes
```
comm_oi_change  = week-over-week change in comm net
lrg_oi_change   = week-over-week change in lrg net
sml_oi_change   = week-over-week change in sml net
total_oi_change = week-over-week change in total OI

driver = argmax(|comm_oi_change|, |lrg_oi_change|, |sml_oi_change|)
```

### 5.10 Trend Analysis
```
cum_4w   = net_position.diff(4)     # 4-week cumulative change
cum_13w  = net_position.diff(13)
cum_26w  = net_position.diff(26)
roc_4w   = (net_position / net_position.shift(4) - 1) * 100
vs_ma    = net_position - net_position.rolling(13).mean()
```

### 5.11 Market Maker Spreading
```
spreading_pct = spreading_positions / open_interest * 100
spreading_percentile = percentile_rank(spreading_pct, N)
```

---

## 6. Application Architecture

### Chosen Approach: CSV Config + Terminal Output + Optional HTML Charts

**No dashboard / no Streamlit.** User interaction is entirely through two CSV files:

| File | Purpose |
|---|---|
| `user_input/user_config.csv` | All global settings — edit the `value` column |
| `user_input/instruments.csv` | Which instruments to run — set `enabled = True/False` |

**Run:** `python main.py` → reads CSVs → calculates → outputs to terminal and/or `output/` folder.

**Why CSV config:**
- Self-documenting (description + notes columns right next to the value)
- Editable in Excel, LibreOffice Calc, or any text editor
- Version-controllable (git diff shows exactly what changed)
- Zero UI code to maintain
- Can be pre-configured per use case (e.g. `metals_only.csv`, `full_analysis.csv`)

**Output options (set via `output_mode` in user_config.csv):**
- `terminal` — Rich colored tables printed to console
- `csv` — Results saved to `output/` as CSV files
- `both` — Both simultaneously

**Charts (optional):**
- `show_chart = True` → saves interactive Plotly HTML chart per instrument to `output/`
- Opens in browser, no server needed

**Why Rich (terminal):**
- Colored tables with headers, borders, and cell-level coloring
- No browser needed for quick daily checks
- Works in any terminal

---

## 7. Project Folder Structure

```
/home/imagda/_invest2024/python/cot_analyzer/
│
├── PROJECT_PLAN.md              ← this file
│
├── data/                        ← downloaded & cached CFTC data
│   ├── cache/                   ← local parquet cache per year
│   └── raw/                     ← raw downloaded ZIPs
│
├── src/
│   ├── __init__.py
│   ├── fetcher.py               ← CFTC data download & caching
│   ├── parser.py                ← CSV parsing, instrument filtering
│   ├── calculator.py            ← WillCo, COT Index, Percentile, signals
│   ├── signals.py               ← Market State, Confluence, OI analysis
│   ├── instruments.py           ← CFTC code mapping, asset metadata
│   └── utils.py                 ← Helpers (smoothing, percentile rank, etc.)
│
├── app/
│   ├── streamlit_app.py         ← Main Streamlit dashboard
│   ├── charts.py                ← Plotly chart builders
│   └── tables.py                ← Table renderers (Streamlit + Rich)
│
├── cli/
│   └── cot_cli.py               ← Terminal CLI (Rich tables, quick lookup)
│
├── tests/
│   ├── test_calculator.py
│   ├── test_fetcher.py
│   └── test_signals.py
│
├── requirements.txt
└── README.md
```

---

## 8. Dashboard Layout (Streamlit)

Modeled on tradeviZion's 9-group structure:

```
┌─────────────────────────────────────────────────────────┐
│  🏆 COT Analyzer — Larry Williams Method                 │
├─────────────────────────────────────────────────────────┤
│  SIDEBAR                  │  MAIN PANEL                  │
│                           │                              │
│  Instrument: [GC Gold ▼]  │  ┌──────────────────────┐   │
│  Report Type: [Legacy ▼]  │  │  WillCo Chart        │   │
│  Analysis: [WillCo ▼]     │  │  (Commercial / Lrg / │   │
│  Lookback: [Auto] [13w]   │  │   Small Spec lines)  │   │
│  Smoothing: [None ▼]      │  └──────────────────────┘   │
│  Extreme Level: [74%] [26%]│                             │
│                           │  ┌──────────────────────┐   │
│  Show sections:           │  │  Net Positions Chart  │   │
│  ✓ Current Positions      │  └──────────────────────┘   │
│  ✓ OI Analysis            │                              │
│  ✓ Analysis               │  ┌──────────────────────┐   │
│  ✓ Trading Signals        │  │  Open Interest Chart  │   │
│  ✓ Historical             │  └──────────────────────┘   │
│  ✓ Trend Analysis         │                              │
│  ✓ Market Maker           │  📋 MAIN TABLE               │
│                           │  (Full / Compact toggle)     │
│  [Refresh Data]           │                              │
│  Last update: Fri 3:30pm  │  📊 HISTORICAL TABLE          │
│                           │  1M | 3M | 6M | 1Y | 3Y | All│
└───────────────────────────┴──────────────────────────────┘
```

---

## 9. Main Table Sections (mirrors tradeviZion Full Mode)

| # | Section | Key fields |
|---|---|---|
| 1 | ⚙️ Settings | Report type, CFTC code, last update date |
| 2 | 📊 Current Positions | Long, Short, Net for each group |
| 3 | 📊 OI Analysis | Total OI, Δ change, driver (who), concentration Top4/Top8 |
| 4 | 📈 Analysis | WillCo %, LW Index %, Percentile %, Market State |
| 5 | 🎯 Trading Signals | Entry (LONG/SHORT/Wait), Signal combo, Accuracy %, Best Setup |
| 6 | 💡 Trading Tips | Context-aware text based on current state |
| 7 | 📈 Trend Analysis | Direction, Strength, Consistency, 4W/13W/26W cumulative Δ, ROC, vs MA |
| 8 | 🔄 Market Maker | Spreading %, Percentile, 13W trend, Activity Level |

---

## 10. Technology Stack

| Layer | Library | Purpose |
|---|---|---|
| Data fetch | `cot-reports` + `requests` | CFTC download + fallback |
| Data processing | `pandas`, `numpy` | DataFrame operations, calculations |
| Caching | `parquet` (via pandas) | Local cache to avoid re-downloading |
| Dashboard | `streamlit` | Web UI, no HTML/CSS needed |
| Charts | `plotly` | Interactive COT line charts |
| CLI tables | `rich` | Colored terminal tables |
| Scheduling | `schedule` or `apscheduler` | Auto-refresh on Fridays |
| Testing | `pytest` | Unit tests for calculations |

### requirements.txt
```
cot-reports>=0.1.3
pandas>=2.0
numpy>=1.24
plotly>=5.0
streamlit>=1.30
rich>=13.0
requests>=2.31
pyarrow>=14.0        # for parquet cache
apscheduler>=3.10    # for weekly auto-update
pytest>=7.0
```

---

## 11. Data Flow

```
CFTC Website (ZIP files)
        │
        ▼
fetcher.py
  - Check local cache (parquet)
  - If stale (older than Friday 3:30pm ET): download new ZIP
  - Unzip → parse CSV → save to parquet cache
        │
        ▼
parser.py
  - Filter by CFTC code
  - Select relevant columns
  - Sort by date
  - Return clean DataFrame (weekly rows, all groups)
        │
        ▼
calculator.py
  - Compute net positions
  - Apply smoothing (if selected)
  - Calculate WillCo Index (primary)
  - Calculate LW Index (secondary)
  - Calculate Percentile (tradeviZion method)
  - Calculate historical percentile ranks (1M/3M/6M/1Y/3Y/All)
  - Compute OI analysis (who drives changes)
  - Compute trend analysis (cum change, ROC, vs MA)
  - Compute market maker spreading
        │
        ▼
signals.py
  - Calculate Market State score → label
  - Detect Confluence signals (bull/bear)
  - Detect Divergence (requires price data — optional)
  - Generate Best Setup + accuracy
  - Build Trading Tips text
        │
        ▼
app/streamlit_app.py        cli/cot_cli.py
  - Render charts              - Rich tables
  - Render tables              - Single instrument
  - Sidebar controls           - Quick terminal lookup
  - Historical comparison
```

---

## 12. Key Design Decisions

### 12.1 LW Index vs Percentile
- **Default: WillCo Index** (LW's OI-adjusted method) — our v5 methodology
- **Available: Percentile** (tradeviZion's preferred — excludes current bar, can exceed 0–100%)
- **Available: Standard LW Index** (always 0–100%, includes current bar)
- User selects via dropdown

### 12.2 Auto Lookback (tradeviZion approach)
```python
AUTO_LOOKBACK = {
    "Metal":  13,   # ~3 months
    "Energy": 13,
    "Index":  13,
    "Bond":   52,   # 1 year
    "FX":     26,   # 6 months
    "Grain":  26,
    "Crypto": 26,
}
```

### 12.3 Caching Strategy
- Store one parquet file per year per report type
- Check if current week's data is present before downloading
- Never re-download historical years (immutable)
- Only re-fetch current year's file each Friday

### 12.4 Price Data (for Divergence)
- COT data alone doesn't include price
- Optional: use `yfinance` to fetch price data for divergence detection
- Divergence is optional feature (Phase 2)

### 12.5 No TradingView Dependency
- Zero reliance on TradingView APIs, Pine Script, or LibraryCOT
- All data from CFTC directly
- All calculations in pure Python/pandas

---

## 13. Development Phases

### Phase 1 — Core (MVP)
- [ ] `fetcher.py` — download + cache CFTC Legacy data
- [ ] `parser.py` — filter instruments, clean columns
- [ ] `calculator.py` — net positions, WillCo, LW Index, Percentile
- [ ] `instruments.py` — CFTC code mapping
- [ ] Basic Streamlit app with WillCo chart + main table
- [ ] `cot_cli.py` — Rich terminal table for single instrument

### Phase 2 — Full Analysis
- [ ] `signals.py` — Market State, Confluence, Best Setup, Trading Tips
- [ ] Historical comparison table (1M/3M/6M/1Y/3Y/All)
- [ ] Trend Analysis section
- [ ] OI Analysis section (who drives changes)
- [ ] Market Maker spreading section
- [ ] Disaggregated + Financial report types

### Phase 3 — Polish & Automation
- [ ] Auto-refresh scheduler (Fridays 3:30pm ET)
- [ ] Price data integration (yfinance) for divergence
- [ ] Multi-instrument dashboard (compare metals side by side)
- [ ] Export to CSV/Excel
- [ ] Unit tests
- [ ] Color themes (Dark/Light)

---

## 14. CLI Usage (planned)

```bash
# Quick lookup — single instrument
python -m cot_analyzer GC

# With options
python -m cot_analyzer GC --report legacy --lookback 13 --method willco

# Compare all metals
python -m cot_analyzer --metals

# Launch Streamlit dashboard
streamlit run app/streamlit_app.py

# Force refresh from CFTC
python -m cot_analyzer --refresh
```

---

## 15. Sources

- [CFTC COT Reports](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [CFTC Historical Compressed](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm)
- [cot-reports PyPI](https://pypi.org/project/cot-reports/)
- [cot-reports GitHub](https://github.com/NDelventhal/cot_reports)
- [pycot GitHub](https://github.com/philsv/pycot)
- [cftc-cot GitHub](https://github.com/Mcamin/cftc-cot)
- [tradeviZion indicator](https://www.tradingview.com/script/uxZcuIjG-Larry-Williams-COT-Analysis-Enhanced-tradeviZion/)

---

*Document version: 1.0 — 2026-03-03*
*Next step: Phase 1 implementation — start with fetcher.py*
