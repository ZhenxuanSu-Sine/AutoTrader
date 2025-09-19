# AutoTrader

一个极简的端到端量化回测脚手架：**AKShare 拉取行情 → 统一 CSV Schema → Backtrader 回测 → 输出基础指标**。适合做低频/低算力的入门与原型验证，后续可扩展到自定义因子、数据库存储与更丰富的评估。

## 快速上手（Windows 11 + conda）

> 需要已安装 [Anaconda](https://www.anaconda.com/products/distribution)。

```bat
:: 1) 创建并激活环境（Python 3.10 建议）
conda create -n autotrader python=3.10 -y
conda activate autotrader

:: 2) 安装依赖
conda install -c conda-forge numpy pandas matplotlib pytz joblib -y
pip install backtrader akshare quantstats

:: 3) （可选）Jupyter
conda install -c conda-forge jupyterlab ipykernel -y
python -m ipykernel install --user --name autotrader --display-name "Python (autotrader)"
```

## 一把梭：从数据到回测

1. **用 AKShare 拉日线行情 → 存 CSV（统一 6 列：`datetime, open, high, low, close, volume`）**

```bash
python data/fetch_akshare_data.py ^
  --symbol 600519 ^
  --start 20220101 --end 20241231 ^
  --adjust qfq ^
  --outfile data/sample_600519.csv
```

2. **跑两个 baseline 策略（买入持有、随机交易）**

```bash
# 在仓库根目录执行
python -m evaluation.evaluate ^
  --data-file data/sample_600519.csv ^
  --strategy buy_hold ^
  --capital 100000

python -m evaluation.evaluate ^
  --data-file data/sample_600519.csv ^
  --strategy random ^
  --capital 100000
```

3. **看输出**
   终端会打印期末资金、简单收益等。更多参数请看 `evaluation/evaluate.py`（手续费 `--commission`、滑点 `--slippage` 等）。

> 备注：评估脚本默认把 CSV 读成 `bt.feeds.PandasData`，只要符合上面的 6 列合同，任何来源都能即插即用（AKShare/自建库导出/其它接口）。

## 目录结构

* `framework/`：通用基类与工具（如 `BaseStrategy`）。
* `data/`：数据获取脚本（此处使用 AKShare）。
* `decision/`：策略实现（如 `buy_and_hold.py`、`random_trader.py`）。
* `evaluation/`：回测与评估 CLI（`evaluate.py`）。

## 可选：本地机密管理（`.env`）

本仓库的 AKShare 不需要 token；如果你后续接入需要凭据的服务，建议用 `.env`：

1. 建模板：`.env.example`（示例：`FOO_TOKEN=your_token_here`）
2. 本地复制生成 `.env`，填入真实值；`.gitignore` 忽略 `.env`
3. 代码里用 `python-dotenv` 读取：

```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv, find_dotenv
import os
load_dotenv(find_dotenv())
secret = os.getenv("FOO_TOKEN")
```

## 参考

* **AKShare**：开源金融数据接口库，覆盖股票/期货/基金/外汇等多市场数据。使用前请阅读其文档与数据源说明：

  * GitHub: [https://github.com/akfamily/akshare](https://github.com/akfamily/akshare)
  * 文档: [https://akshare.xyz](https://akshare.xyz)
* **Backtrader**：Python 回测与交易框架：[https://www.backtrader.com/](https://www.backtrader.com/)