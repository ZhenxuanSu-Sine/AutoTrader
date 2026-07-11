# 导入聚宽函数库
import jqdata


# 权重 CSV 文件路径，需先上传到聚宽「研究」模块的私有文件空间。
# read_file(path) 的 path 是相对私有空间根目录的路径。
WEIGHTS_FILE = 'small_account_best_weights.csv'

# 小资金实盘/模拟交易约束：可以按自己的账户规模调整。
MAX_POSITIONS = 5
MIN_POSITION_VALUE = 8000.0
CASH_BUFFER = 0.1
LOT_SIZE = 100


def load_weights(path):
    """使用聚宽 read_file 读取 AutoTrader 导出的 date,code,weight CSV。"""
    raw = read_file(path)
    if isinstance(raw, bytes):
        text = raw.decode('utf-8-sig')
    else:
        text = raw

    rows = text.strip().splitlines()
    weights = {}
    for line in rows[1:]:
        if not line.strip():
            continue
        date, code, weight = line.split(',')
        weights.setdefault(date, {})[code] = float(weight)
    return weights


def last_price(security):
    """取当前价格；若当前快照不可用则退回到最近日收盘价。"""
    try:
        price = get_current_data()[security].last_price
        if price and price > 0:
            return float(price)
    except Exception:
        pass
    try:
        hist = attribute_history(security, 1, '1d', ['close'])
        if len(hist) > 0:
            return float(hist['close'][-1])
    except Exception:
        pass
    return None


def round_lot(amount):
    return int(amount / LOT_SIZE) * LOT_SIZE


def build_target_amounts(context, raw_targets):
    """把目标权重转换成适合小资金账户的一手整数股数。"""
    portfolio_value = context.portfolio.total_value * (1 - CASH_BUFFER)
    ranked = sorted(raw_targets.items(), key=lambda item: item[1], reverse=True)
    selected = ranked[:MAX_POSITIONS]
    total_weight = sum(weight for _, weight in selected)
    if total_weight <= 0:
        return {}

    targets = {}
    for security, weight in selected:
        price = last_price(security)
        if price is None or price <= 0:
            log.info('Skip %s: invalid price' % security)
            continue
        target_value = portfolio_value * weight / total_weight
        if target_value < MIN_POSITION_VALUE:
            continue
        amount = round_lot(target_value / price)
        if amount >= LOT_SIZE:
            targets[security] = amount
    return targets


# 初始化函数，设定基准、复权模式和运行频率
def initialize(context):
    # 沪深300作为默认基准，可按需要改成 000905.XSHG / 000852.XSHG 等
    set_benchmark('000300.XSHG')
    # 开启动态复权模式（真实价格）
    set_option('use_real_price', True)
    # 读取私有文件中的目标权重
    g.weights = load_weights(WEIGHTS_FILE)
    log.info('Loaded target weights from %s, rebalance_days=%d' % (
        WEIGHTS_FILE, len(g.weights)
    ))
    # 日频策略：每天开盘检查当天是否为调仓日
    run_daily(market_open, time='open')


# 每个交易日开盘调用；只有当天在权重表中时才调仓
def market_open(context):
    today = context.current_dt.strftime('%Y-%m-%d')
    raw_targets = g.weights.get(today)
    if not raw_targets:
        return

    target_amounts = build_target_amounts(context, raw_targets)
    current = set(context.portfolio.positions.keys())
    target_codes = set(target_amounts.keys())

    # 不在本期可交易目标组合内的持仓清零；用 order_target 按股数清仓。
    for security in current - target_codes:
        position = context.portfolio.positions[security]
        if position.closeable_amount > 0:
            order_target(security, 0)

    # 调整目标持仓。小于一手的差额不动，避免碎股/不足一手报错。
    for security, target_amount in target_amounts.items():
        position = context.portfolio.positions.get(security, None)
        current_amount = position.total_amount if position else 0
        if abs(target_amount - current_amount) < LOT_SIZE:
            continue
        order_target(security, target_amount)

    log.info('Rebalanced %s, raw=%d, tradable=%d' % (
        today, len(raw_targets), len(target_amounts)
    ))
    record(holding_count=len(target_amounts))
