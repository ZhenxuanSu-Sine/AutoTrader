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
    """Convert canonical A-share symbols to JoinQuant security codes."""

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
    joinquant_max_positions: int = 20,
    joinquant_min_position_value: float = 5_000.0,
    joinquant_cash_buffer: float = 0.02,
    joinquant_lot_size: int = 100,
) -> JoinQuantExportResult:
    """Export ``timestamp/symbol/weight`` rows as JoinQuant target weights.

    CSV schema:

    - ``date``: rebalance date, ``YYYY-MM-DD``
    - ``code``: JoinQuant security code, such as ``600519.XSHG``
    - ``weight``: target portfolio weight

    Generated JoinQuant helpers read the CSV via ``read_file(path)`` and
    convert weights into board-lot target shares. This is intentional: for a
    small personal account, directly submitting tiny target values causes many
    invalid odd-lot close/open orders in JoinQuant.
    """

    required = {"timestamp", "symbol", "weight"}
    missing = required - set(weights.columns)
    if missing:
        raise ValueError(f"weights missing columns: {sorted(missing)}")
    if min_weight < 0:
        raise ValueError("min_weight must be non-negative")
    if joinquant_max_positions < 1:
        raise ValueError("joinquant_max_positions must be positive")
    if joinquant_min_position_value < 0:
        raise ValueError("joinquant_min_position_value must be non-negative")
    if not 0 <= joinquant_cash_buffer < 1:
        raise ValueError("joinquant_cash_buffer must be in [0, 1)")
    if joinquant_lot_size < 1:
        raise ValueError("joinquant_lot_size must be positive")

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
        py_output.write_text(
            _joinquant_python_template(
                private_path,
                max_positions=joinquant_max_positions,
                min_position_value=joinquant_min_position_value,
                cash_buffer=joinquant_cash_buffer,
                lot_size=joinquant_lot_size,
            ),
            encoding="utf-8",
        )

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


def _joinquant_python_template(
    joinquant_weights_path: str,
    *,
    max_positions: int,
    min_position_value: float,
    cash_buffer: float,
    lot_size: int,
) -> str:
    return (
        "# 导入聚宽函数库\n"
        "import jqdata\n\n\n"
        "# 权重 CSV 文件路径，需先上传到聚宽「研究」模块的私有文件空间。\n"
        "# read_file(path) 的 path 是相对私有空间根目录的路径。\n"
        f"WEIGHTS_FILE = {joinquant_weights_path!r}\n\n"
        "# 小资金实盘/模拟交易约束：可以按自己的账户规模调整。\n"
        f"MAX_POSITIONS = {max_positions}\n"
        f"MIN_POSITION_VALUE = {float(min_position_value)!r}\n"
        f"CASH_BUFFER = {float(cash_buffer)!r}\n"
        f"LOT_SIZE = {int(lot_size)}\n\n\n"
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
        "def last_price(security):\n"
        "    \"\"\"取当前价格；若当前快照不可用则退回到最近日收盘价。\"\"\"\n"
        "    try:\n"
        "        price = get_current_data()[security].last_price\n"
        "        if price and price > 0:\n"
        "            return float(price)\n"
        "    except Exception:\n"
        "        pass\n"
        "    try:\n"
        "        hist = attribute_history(security, 1, '1d', ['close'])\n"
        "        if len(hist) > 0:\n"
        "            return float(hist['close'][-1])\n"
        "    except Exception:\n"
        "        pass\n"
        "    return None\n\n\n"
        "def round_lot(amount):\n"
        "    return int(amount / LOT_SIZE) * LOT_SIZE\n\n\n"
        "def build_target_amounts(context, raw_targets):\n"
        "    \"\"\"把目标权重转换成适合小资金账户的一手整数股数。\"\"\"\n"
        "    portfolio_value = context.portfolio.total_value * (1 - CASH_BUFFER)\n"
        "    ranked = sorted(raw_targets.items(), key=lambda item: item[1], reverse=True)\n"
        "    selected = ranked[:MAX_POSITIONS]\n"
        "    total_weight = sum(weight for _, weight in selected)\n"
        "    if total_weight <= 0:\n"
        "        return {}\n"
        "\n"
        "    targets = {}\n"
        "    for security, weight in selected:\n"
        "        price = last_price(security)\n"
        "        if price is None or price <= 0:\n"
        "            log.info('Skip %s: invalid price' % security)\n"
        "            continue\n"
        "        target_value = portfolio_value * weight / total_weight\n"
        "        if target_value < MIN_POSITION_VALUE:\n"
        "            continue\n"
        "        amount = round_lot(target_value / price)\n"
        "        if amount >= LOT_SIZE:\n"
        "            targets[security] = amount\n"
        "    return targets\n\n\n"
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
        "    raw_targets = g.weights.get(today)\n"
        "    if not raw_targets:\n"
        "        return\n"
        "\n"
        "    target_amounts = build_target_amounts(context, raw_targets)\n"
        "    current = set(context.portfolio.positions.keys())\n"
        "    target_codes = set(target_amounts.keys())\n"
        "\n"
        "    # 不在本期可交易目标组合内的持仓清零；用 order_target 按股数清仓。\n"
        "    for security in current - target_codes:\n"
        "        position = context.portfolio.positions[security]\n"
        "        if position.closeable_amount > 0:\n"
        "            order_target(security, 0)\n"
        "\n"
        "    # 调整目标持仓。小于一手的差额不动，避免碎股/不足一手报错。\n"
        "    for security, target_amount in target_amounts.items():\n"
        "        position = context.portfolio.positions.get(security, None)\n"
        "        current_amount = position.total_amount if position else 0\n"
        "        if abs(target_amount - current_amount) < LOT_SIZE:\n"
        "            continue\n"
        "        order_target(security, target_amount)\n"
        "\n"
        "    log.info('Rebalanced %s, raw=%d, tradable=%d' % (\n"
        "        today, len(raw_targets), len(target_amounts)\n"
        "    ))\n"
        "    record(holding_count=len(target_amounts))\n"
    )
