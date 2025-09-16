# AutoTrader

This repository contains a very simple end‑to‑end framework for building and
evaluating automated trading strategies.  The goal of this project is to
provide a **minimal working example** showing how to set up a Backtrader‑based
backtesting environment, fetch data from [Tushare](https://tushare.pro),
write trivial strategies (such as buy‑and‑hold or random trading) and
generate basic performance metrics.  Once you are comfortable with the
framework you can extend it by adding your own data sources (for example
PostgreSQL databases with custom factors), more sophisticated strategies and
richer evaluation reports.

## Getting started on Windows 11

These instructions assume you are running **Windows 11** and have
[Anaconda](https://www.anaconda.com/products/distribution) installed.  If
Anaconda is not installed yet, download and install it first.  The
following steps create a fresh Python environment and install the
dependencies required by this project.

```batch
:: 1. Create a new conda environment with Python 3.10
conda create -n autotrader python=3.10 -y

:: 2. Activate the environment
conda activate autotrader

:: 3. Install core scientific packages from the conda‑forge channel
conda install -c conda-forge numpy pandas matplotlib pytz joblib -y

:: 4. Install Backtrader using pip (Backtrader is not available on
::    conda-forge at the time of writing)
pip install backtrader

:: 5. Install Tushare and other data/analysis libraries
pip install tushare quantstats

:: 6. (Optional) Install JupyterLab for notebooks
conda install -c conda-forge jupyterlab ipykernel -y

:: 7. Register the kernel for notebooks (optional)
python -m ipykernel install --user --name autotrader --display-name "Python (autotrader)"

:: 8. (Optional) Install extra libraries for machine learning
pip install scikit-learn xgboost lightgbm

```

> **Note**
>
> Some data provided by Tushare require a token.  Visit
> <https://tushare.pro> to register and obtain a personal API token.
> Once you have the token you can set it in your scripts via
>
> ```python
> import tushare as ts
> ts.set_token("YOUR_TUSHARE_TOKEN")
> pro = ts.pro_api()
> ```

## Repository layout

The project is organised into four main modules.  Each module has its own
subdirectory under the repository root:

| Directory          | Purpose                                                            |
|--------------------|--------------------------------------------------------------------|
| `framework/`       | Generic classes and utilities used across strategies and backtests. |
| `data/`            | Scripts for downloading and preparing market data.                  |
| `decision/`        | Individual trading strategies (decision logic).                    |
| `evaluation/`      | Code for running backtests and computing simple metrics.           |

You can extend or modify this structure to suit your own workflow.  For
example, if you plan to store your own factors in a PostgreSQL database you
could add a `storage/` module containing an ORM or database helper classes.

## Usage examples

The simplest way to explore the framework is to run one of the trivial
strategies provided under `decision/`.  The commands below assume you
have downloaded at least a few days of daily bars for a stock symbol
using the `data/fetch_tushare_data.py` script (see that file for
details).  This example will run two strategies – a buy‑and‑hold
strategy and a random trading strategy – on the same dataset and
report some basic results:

```bash
# Activate your environment first
conda activate autotrader

# Change into the project directory and run the evaluation
python evaluation/evaluate.py \
    --data-file data/sample_000001.SZ.csv \
    --strategy buy_hold \
    --capital 100000

python evaluation/evaluate.py \
    --data-file data/sample_000001.SZ.csv \
    --strategy random \
    --capital 100000

```

Both commands print final portfolio value and other statistics to the
console.  See `evaluation/evaluate.py` for more options such as
changing the commission, slippage or time range.

## Contributing

This project is intended as a lightweight starting point.  Feel free to
fork the repository and add new strategies, additional data
connectors, visualisation tools or machine learning models.  Pull
requests are welcome!