"""Export target-weight strategies to JoinQuant-compatible files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class JoinQuantExportResult:
    csv_path: Path
    python_path: Path | None
    summary_path: Path
    input_rows: int
    exported_rows: int
    dropped_rows: int
    dates: int
    securities: int


def csmar_symbol_to_joinquant(symbol: str, *, include_unsupported: bool = False) -> str | None:
    """Convert canonical A-share symbols to JoinQuant security codes.

    Supported conversions:

    - ``600000.SH`` -> ``600000.XSHG``
    - ``000001.SZ`` -> ``000001.XSHE``

    North Exchange symbols are returned only when ``include_unsupported`` is
    true, because they may not be usable in all JoinQuant environments.
    """

    value = str(symbol).strip().upper()
    if value.endswith(".XSHG") or value.endswith(".XSHE"):
        return value
    if value.endswith(".SH"):
        return value[:-3] + ".XSHG"
    if value.endswith(".SZ"):
        return value[:-3] + ".XSHE"
    if value.endswith(".BJ"):
        return value[:-3] + ".BJ" if include_unsupported else None
    if len(value) == 6 and value.isdigit():
        if value.startswith(("5", "6", "9")):
            return value + ".XSHG"
        if value.startswith(("0", "1", "2", "3")):
            return value + ".XSHE"
    return value if include_unsupported else None


def export_joinquant_weights(
    weights: pd.DataFrame,
    csv_path: str | Path,
    *,
    python_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    joinquant_weights_path: str | None = None,
    include_unsupported: bool = False,
    min_weight: float = 0.0,
) -> JoinQuantExportResult:
    """Export ``timestamp/symbol/weight`` rows as JoinQuant target weights.

    CSV schema:

    - ``date``: rebalance date, ``YYYY-MM-DD``
    - ``code``: JoinQuant security code, such as ``600519.XSHG``
    - ``weight``: target portfolio weight

    Generated JoinQuant helpers read this CSV through ``read_file(path)`` and
    submit target values with ``order_target_value``.
    """

    required = {"timestamp", "symbol", "weight"}
    missing = required - set(weights.columns)
    if missing:
        raise ValueError(f"weights missing columns: {sorted(missing)}")
    if min_weight < 0:
        raise ValueError("min_weight must be non-negative")

    data = weights[list(required)].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["weight"] = pd.to_numeric(data["weight"], errors="raise")
    data = data[data["weight"] > min_weight].copy()
    data["code"] = data["symbol"].map(
        lambda value: csmar_symbol_to_joinquant(
            value, include_unsupported=include_unsupported
        )
    )
    dropped = int(data["code"].isna().sum())
    exported = data[data["code"].notna()].copy()
    exported["date"] = exported["timestamp"].dt.strftime("%Y-%m-%d")
    exported = exported[["date", "code", "weight"]].sort_values(["date", "code"])

    csv_output = Path(csv_path)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    exported.to_csv(csv_output, index=False, encoding="utf-8-sig")

    py_output = Path(python_path) if python_path is not None else None
    if py_output is not None:
        py_output.parent.mkdir(parents=True, exist_ok=True)
        private_path = joinquant_weights_path or csv_output.name
        py_output.write_text(_joinquant_python_template(private_path), encoding="utf-8")

    summary_output = (
        Path(summary_path) if summary_path is not None else csv_output.with_suffix(".summary.csv")
    )
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary = (
        exported.groupby("date")
        .agg(securities=("code", "nunique"), gross_weight=("weight", "sum"))
        .reset_index()
    )
    summary.to_csv(summary_output, index=False, encoding="utf-8-sig")

    return JoinQuantExportResult(
        csv_path=csv_output,
        python_path=py_output,
        summary_path=summary_output,
        input_rows=int(len(weights)),
        exported_rows=int(len(exported)),
        dropped_rows=dropped,
        dates=int(exported["date"].nunique()) if not exported.empty else 0,
        securities=int(exported["code"].nunique()) if not exported.empty else 0,
    )


def _joinquant_python_template(joinquant_weights_path: str) -> str:
    return (
        "# 导入聚宽函数库\n"
        "import jqdata\n\n\n"
        "# 权重 CSV 文件路径，需先上传到聚宽「研究」模块的私有文件空间。\n"
        "# read_file(path) 的 path 是相对私有空间根目录的路径。\n"
        f"WEIGHTS_FILE = {joinquant_weights_path!r}\n\n\n"
        "def load_weights(path):\n"
        "    \"\"\"使用聚宽 read_file 读取 AutoTrader 导出的 date,code,weight CSV。\"\"\"\n"
        "    raw = read_file(path)\n"
        "    if isinstance(raw, bytes):\n"
        "        text = raw.decode('utf-8-sig')\n"
        "    else:\n"
        "        text = raw\n"
        "\n"
        "    rows = text.strip().splitlines()\n"
        "    weights = {}\n"
        "    for line in rows[1:]:\n"
        "        if not line.strip():\n"
        "            continue\n"
        "        date, code, weight = line.split(',')\n"
        "        weights.setdefault(date, {})[code] = float(weight)\n"
        "    return weights\n\n\n"
        "# 初始化函数，设定基准、复权模式和运行频率\n"
        "def initialize(context):\n"
        "    # 沪深300作为默认基准，可按需要改成 000905.XSHG / 000852.XSHG 等\n"
        "    set_benchmark('000300.XSHG')\n"
        "    # 开启动态复权模式（真实价格）\n"
        "    set_option('use_real_price', True)\n"
        "    # 读取私有文件中的目标权重\n"
        "    g.weights = load_weights(WEIGHTS_FILE)\n"
        "    log.info('Loaded target weights from %s, rebalance_days=%d' % (\n"
        "        WEIGHTS_FILE, len(g.weights)\n"
        "    ))\n"
        "    # 日频策略：每天开盘检查当天是否为调仓日\n"
        "    run_daily(market_open, time='open')\n\n\n"
        "# 每个交易日开盘调用；只有当天在权重表中时才调仓\n"
        "def market_open(context):\n"
        "    today = context.current_dt.strftime('%Y-%m-%d')\n"
        "    targets = g.weights.get(today)\n"
        "    if not targets:\n"
        "        return\n"
        "\n"
        "    current = set(context.portfolio.positions.keys())\n"
        "    target_codes = set(targets.keys())\n"
        "\n"
        "    # 不在本期目标组合内的持仓清零\n"
        "    for security in current - target_codes:\n"
        "        order_target_value(security, 0)\n"
        "\n"
        "    portfolio_value = context.portfolio.total_value\n"
        "\n"
        "    # 按目标权重调仓：权重需换算成聚宽 order_target_value 接受的目标市值。\n"
        "    for security, weight in targets.items():\n"
        "        order_target_value(security, portfolio_value * weight)\n"
        "\n"
        "    log.info('Rebalanced %s, holdings=%d, gross_weight=%.4f' % (\n"
        "        today, len(targets), sum(targets.values())\n"
        "    ))\n"
        "    record(gross_weight=sum(targets.values()), holding_count=len(targets))\n"
    )
