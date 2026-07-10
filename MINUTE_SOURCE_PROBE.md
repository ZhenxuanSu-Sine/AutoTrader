# 免费分钟数据接口探针

日期：2026-07-08

目标：验证 BaoStock 5 分钟接口和 AKShare 1 分钟接口在当前本地环境是否可用。

## 结论

### AKShare / Sina `stock_zh_a_minute`

可用，适合做“近期分钟数据增量缓存”。

本地测试标的：`sz000001`

| period | 状态 | 行数 | 起始时间 | 结束时间 | 字段 |
|---:|---|---:|---|---|---|
| 1 | OK | 1970 | 2026-06-25 13:53:00 | 2026-07-07 15:00:00 | day, open, high, low, close, volume |
| 5 | OK | 1970 | 2026-05-08 14:55:00 | 2026-07-07 15:00:00 | day, open, high, low, close, volume |
| 15 | OK | 1970 | 2025-12-29 14:45:00 | 2026-07-07 15:00:00 | day, open, high, low, close, volume |
| 30 | OK | 1970 | 2025-07-01 14:30:00 | 2026-07-07 15:00:00 | day, open, high, low, close, volume |
| 60 | OK | 1970 | 2024-06-25 14:00:00 | 2026-07-07 15:00:00 | day, open, high, low, close, volume |

额外测试：

- `sh600519`
- `sz000001`
- `sh600000`
- `sz300750`

这些标的在 1/5/15/30/60 分钟周期上都成功返回。

注意：

- 该接口每个周期固定返回约 1970 条，历史长度随周期变长而变长。
- 1 分钟只能覆盖最近约 8 个交易日，不适合一次性回填多年分钟历史。
- 支持 `adjust=''/'qfq'/'hfq'`，但字段只有 OHLCV，没有涨跌停价、停牌、前收等回测辅助字段。

### AKShare / EastMoney `stock_zh_a_hist_min_em`

当前本机不可用。

测试：

- `symbol='000001'`
- `period='1'`
- `start_date='2024-01-02 09:30:00'`
- `end_date='2024-01-02 15:00:00'`

结果：

- 默认环境：`ProxyError`，访问 `push2his.eastmoney.com` 时被不可用代理拦截。
- 清空代理环境后：`RemoteDisconnected`。

判断：

这个接口理论上更接近“历史分钟回填”，但当前网络/上游限制下不稳定。暂不作为主数据源。

### BaoStock `query_history_k_data_plus`

当前本机不可用。

BaoStock 包可正常导入，`www.baostock.com:10030` TCP 端口可连接，但 `bs.login()` 收包超时。

错误：

```text
login 10002007: 网络接收错误。
```

判断：

- BaoStock 官方接口理论上支持 5/15/30/60 分钟 K 线。
- 当前失败点在登录阶段，不是 5 分钟参数问题。
- 可能和网络线路、防火墙、服务端 socket 响应或 BaoStock 服务状态有关。
- 换网络、关闭系统代理、或稍后重试后值得再测。

## 建议

短期先这样走：

1. 用 AKShare/Sina `stock_zh_a_minute` 做近期 1 分钟增量缓存。
2. 每天定时拉取最近 1970 条，去重后落本地 parquet。
3. 对 1 分钟策略，只先做最近几天到几周的小样本实验。
4. BaoStock 暂时不作为自动下载源，等网络可用后再接 5/15/30/60 分钟历史。
5. AKShare/EastMoney 历史分钟暂时标记为不稳定备用源。

如果目标是多年分钟级训练数据，免费源目前还不够稳。更现实的路线是：

- 免费阶段：AKShare/Sina 每日增量积累；
- 可选阶段：找聚宽/JQData 或券商 QMT 补历史分钟；
- 实盘前：用券商行情源作为最终对齐源。

## 复测脚本

```powershell
python scripts\probe_minute_sources.py
```

输出：

- `reports/minute_source_probe/probe.csv`
