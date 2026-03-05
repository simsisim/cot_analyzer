# COT Analyzer

A powerful tool for analyzing Commodity Futures Trading Commission (CFTC) Commitment of Traders (COT) data. It provides quantitative insights into market positioning, commercial hedging, and speculator sentiment through both terminal reports and high-quality charts.

## Features
- **Data Integration**: Automatically fetches raw COT data from CFTC and price data from Yahoo Finance.
- **Quantitative Indicators**: Larry Williams Index, percentile ranks, and WillCo (Williams Commercial Index).
- **ProGo Analysis**: Jake Bernstein's Professional/Amateur sentiment indicator.
- **Visual Analytics**: Professional multi-panel charts featuring candlesticks, net positions, and stochastics.
- **Batch Processing**: Automate multiple investigation runs across different instruments and timeframes.

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd cot_analyzer
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Ensure you have `google-chrome` or `chromium` installed for Plotly chart exports (via Kaleido).*

## Configuration

The application is controlled via two primary files in the `user_input/` directory:

1.  **`user_config.csv`**: Global parameters for analysis (lookback periods, smoothing, output formats, etc.).
2.  **`instruments.csv`**: Define which markets to analyze. Set the `enabled` column to `True` for markers you wish to process by default.

## Usage

### 1. Direct Mode (`main.py`)
Run the analyzer directly for all enabled instruments or use CLI overrides for specific research.

**Basic run**:
```bash
python main.py
```

**Research Overrides**:
```bash
# Process only Gold for a specific 5-year range and add a custom folder tag
python main.py --instrument "GC - Gold" --range "01-01-2000:31-12-2005" --tag "investigation_v1"
```

### 2. Batch Mode (`run_batch.py`)
Automate multiple runs defined in a central configuration file. This is useful for large-scale research projects.

**Standard batch run**:
This will use the default `user_input/batching.csv`.
```bash
python tools/run_batch.py
```

**Custom batch file**:
```bash
python tools/run_batch.py path/to/your_batch_file.csv
```

The batch runner handles unique folder creation automatically, ensuring results for different ranges or instruments are never overwritten.

## Output Structure

Results are stored in the `output/` directory:
- **`output/charts/`**: Standard runs based on `instruments.csv`.
- **`output/charts/research/`**: Results from CLI overrides and Batch Mode, organized by `[Tag]_[DateRange]`.
- **`cot_report.txt / .html`**: Summary reports for the current run.
- **`summary.csv`**: Quantitative data table for all processed instruments.

## Acknowledgments
- Inspired by the work of Larry Williams and Jake Bernstein.
- Powered by `pandas`, `plotly`, and `rich`.
