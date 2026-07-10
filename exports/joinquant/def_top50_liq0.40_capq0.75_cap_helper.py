# 导入聚宽函数库
import jqdata


# 权重 CSV 文件路径，需先上传到聚宽「研究」模块的私有文件空间。
# read_file(path) 的 path 是相对私有空间根目录的路径。
WEIGHTS_FILE = 'def_top50_liq0.40_capq0.75_cap_weights.csv'


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
    targets = g.weights.get(today)
    if not targets:
        return

    current = set(context.portfolio.positions.keys())
    target_codes = set(targets.keys())

    # 不在本期目标组合内的持仓清零
    for security in current - target_codes:
        order_target_value(security, 0)

    portfolio_value = context.portfolio.total_value

    # 按目标权重调仓：权重需换算成聚宽 order_target_value 接受的目标市值。
    for security, weight in targets.items():
        order_target_value(security, portfolio_value * weight)

    log.info('Rebalanced %s, holdings=%d, gross_weight=%.4f' % (
        today, len(targets), sum(targets.values())
    ))
    record(gross_weight=sum(targets.values()), holding_count=len(targets))
