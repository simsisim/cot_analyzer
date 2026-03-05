# COT Analyzer — Methodology & Models

## Data Source

CFTC publishes weekly Commitment of Traders (COT) reports.
Data reflects positions as of **Tuesday**, released every **Friday at 3:30pm ET**.
3-day lag: the latest data is always 3 days old at release.

Three report types available:
| Report | Best for | Groups |
|---|---|---|
| Legacy | Commodities, Metals | Commercial / Non-Commercial / Non-Reportable |
| Disaggregated | Commodities (detailed) | Producer-Merchant / Managed Money / Non-Reportable |
| Financial | Currencies, Indices, Bonds | Dealer / Leveraged Funds / Non-Reportable |

---

## Raw Data Available per Group

From CFTC for each group (Commercial, Large Spec, Small Spec):
```
long positions     (contracts)
short positions    (contracts)
net = long - short (contracts)
open_interest      (total market, all groups)
```

CFTC also pre-calculates and publishes:
```
% of OI Long  = long  / open_interest × 100   ← group's share of all market longs
% of OI Short = short / open_interest × 100   ← group's share of all market shorts
```
Note: % of OI Long + % of OI Short ≠ 100% per group (other groups hold the rest).

---

## Analysis Methods

### Method 1 — Pct_Long  *(no lookback needed)*

```
Pct_Long = long / (long + short) × 100
```

- Shows the **directional bias within the group's own book**
- 50% = perfectly neutral (equal long and short)
- > 50% = long biased
- < 50% = short biased
- Always bounded 0–100%
- **Naturally smooth** — changes only as positions gradually shift
- No lookback window → no parameter to tune
- Similar to the B6J550VX (TradingView cot_report_indicator) approach

### Method 2 — LW_Index  *(lookback required)*

```
LW_Index = (net_current − min_N) / (max_N − min_N) × 100
```

- Original Larry Williams COT Index
- **Includes** the current bar in the min/max range calculation
- Always bounded 0–100%
- Short lookback (13w) → sensitive, fast, spiky
- Long lookback (156w) → smooth, slower to reach extremes
- The **lookback period** is just a parameter of the same formula — it controls sensitivity, not the model

### Method 3 — Percentile  *(lookback required)*

```
shifted_net = net.shift(1)
Percentile = (net_current − min_N of shifted) / (max_N of shifted − min_N of shifted) × 100
```

- tradeviZion variant of LW_Index
- **Excludes** the current bar from range calculation (uses yesterday's range)
- Can exceed 0–100% when today's value breaks historical extremes
- Clamped at -20% / +120% for display readability
- More sensitive to new extremes than LW_Index

### Method 4 — WillCo  *(lookback required)*

- Displays **both LW_Index and Percentile simultaneously** on the same chart
- Solid lines = LW_Index (0–100%)
- Dashed lines = Percentile (can exceed 0–100%)
- Useful for seeing where both methods agree or diverge
- Y-axis extended to -25 / +125 to accommodate Percentile overflow

---

## The Lookback Parameter

The **lookback period** is a single parameter that applies to LW_Index, Percentile, and WillCo.
It controls the size of the historical window for min/max calculation.

| Lookback | Behavior | Appearance |
|---|---|---|
| 13 weeks | Very sensitive, fast signal, hits 0/100 often | Jagged, volatile |
| 26 weeks | LW standard default (6 months) | Moderate |
| 52 weeks | Slower, more confirmation required | Smoother |
| 156 weeks | Very slow, only genuine multi-year extremes | Very smooth |

**Auto mode** (recommended) applies asset-class defaults:
| Asset Class | Auto Lookback |
|---|---|
| Metals | 13w |
| Energy | 13w |
| Index | 13w |
| Bond | 52w |
| FX | 26w |
| Crypto | 26w |

---

## COT Index — Umbrella Term

"COT Index" is the **generic category name** for all normalized positioning methods.
LW_Index, Percentile, and WillCo are all types of COT Index.
It is not a separate calculation — it is the name for the concept of ranking COT positioning.

---

## COT Proximity Index  *(price-based proxy)*

When actual COT data is unavailable (between Tuesday cutoff and Friday release):
```
price_lw       = (close − min_N) / (max_N − min_N) × 100   ← LW formula applied to price
prox_comm      = 100 − price_lw    ← inverted (commercials are contrarian to price)
prox_lrg/sml   = price_lw          ← specs follow the trend
```

- Requires yfinance price data (weekly OHLCV)
- Useful as a mid-week estimate only
- Clearly labelled as a proxy — not actual COT data

---

## Summary Table

| Method | Lookback | Range | Smooth? | Data needed |
|---|---|---|---|---|
| `Pct_Long` | none | 0–100% always | yes (natural) | CFTC only |
| `LW_Index` | yes (N weeks) | 0–100% always | depends on N | CFTC only |
| `Percentile` | yes (N weeks) | -20% to +120% | depends on N | CFTC only |
| `WillCo` | yes (N weeks) | -25% to +125% | depends on N | CFTC only |
| `COT_Proximity` | yes (N weeks) | 0–100% | depends on N | CFTC + price |

---

## Chart Types

| Chart | What it shows | analysis_method |
|---|---|---|
| `COT_Report` | Raw net positions in contracts + OI on secondary axis | n/a |
| `COT_Index` | Normalized index lines (Pct_Long / LW_Index / Percentile / WillCo) | all |
| `COT_Proximity` | Price-based proxy for mid-week estimation | n/a |

*Chart types to display per run: TBD — user decision pending.*
