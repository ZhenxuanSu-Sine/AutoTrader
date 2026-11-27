"""Research backtest for daily Au99.99 signals and next-session execution.

No bank-minute quote is assumed. This is a daily proxy backtest, not the
approved minute-level bank execution strategy.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def normalize_sge(raw: pd.DataFrame) -> pd.DataFrame:
    aliases = {"date": ("date","日期","交易日期"),"open": ("open","开盘价","开盘"),
               "high": ("high","最高价","最高"),"low": ("low","最低价","最低"),
               "close": ("close","收盘价","收盘")}
    cols = {}
    for dest, names in aliases.items():
        found = next((name for name in names if name in raw.columns), None)
        if found is None:
            raise ValueError(f"missing {dest}; available={list(raw.columns)}")
        cols[dest] = found
    df = raw.rename(columns={v:k for k,v in cols.items()})[list(cols)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for key in ("open","high","low","close"):
        df[key] = pd.to_numeric(df[key], errors="coerce")
    df = df.dropna().sort_values("date").drop_duplicates("date").reset_index(drop=True)
    df = df[(df[["open","high","low","close"]]>0).all(axis=1)].reset_index(drop=True)
    if len(df) < 150:
        raise ValueError(f"insufficient real daily bars: {len(df)} < 150")
    return df

def load_data(path: str | None) -> pd.DataFrame:
    if path:
        return normalize_sge(pd.read_csv(path))
    import akshare as ak
    return normalize_sge(ak.spot_hist_sge(symbol="Au99.99"))

def backtest(df: pd.DataFrame, initial=20000.0, spread_per_gram=3.8,
             max_weight=0.8, fast=20, slow=60, execution_lag=1,
             max_holding_days=None, take_profit=None, stop_loss=None):
    if execution_lag < 1: raise ValueError("execution must lag signal at least one bar")
    if max_holding_days is not None and max_holding_days < 1:
        raise ValueError('max_holding_days must be positive')
    for name, value in [('take_profit', take_profit), ('stop_loss', stop_loss)]:
        if value is not None and not (0 < value < 1):
            raise ValueError(f'{name} must be between 0 and 1')
    d = df.copy()
    d["ma_fast"] = d.close.rolling(fast).mean()
    d["ma_slow"] = d.close.rolling(slow).mean()
    d["target"] = np.where(d.ma_fast > d.ma_slow, max_weight, 0.0)
    d.loc[d.ma_slow.isna(), "target"] = 0.0
    d["execution_target"] = d.target.shift(execution_lag).fillna(0.0)
    cash, grams, halted = initial, 0.0, False
    entry_date, entry_price = None, None
    exit_reasons = {'max_holding_days':0, 'take_profit':0, 'stop_loss':0}
    records, trades = [], []
    # The official Xingye 3.8 CNY/g roundtrip spread is represented symmetrically.
    # Proxy assumption, not a verified Alipay bank minute quote.
    half = spread_per_gram/2
    for r in d.itertuples(index=False):
        buy, sell = r.open + half, r.open - half
        if sell <= 0: raise ValueError("invalid spread for historical prices")
        equity_before = cash + grams*sell
        loss = 1-equity_before/initial
        target = 0.0 if halted else float(r.execution_target)
        if loss >= .25: halted, target = True, 0.0
        elif loss >= .20: target = 0.0
        elif loss >= .15: target = min(target, .25)
        # Exit conditions use the current session OPEN only: no intraday
        # high/low assumption and no same-day close lookahead.
        exit_reason = None
        if grams > 1e-10 and entry_date is not None:
            holding_days = (r.date - entry_date).days
            pnl = sell / entry_price - 1
            if stop_loss is not None and pnl <= -stop_loss:
                exit_reason = 'stop_loss'
            elif take_profit is not None and pnl >= take_profit:
                exit_reason = 'take_profit'
            elif max_holding_days is not None and holding_days >= max_holding_days:
                exit_reason = 'max_holding_days'
        if exit_reason:
            target = 0.0
            exit_reasons[exit_reason] += 1
        desired = equity_before*target
        current = grams*sell
        if desired > current+100 and not halted:
            qty = min(cash/buy, (desired-current)/buy)
            if qty*buy >= 100:
                if grams < 1e-10:
                    entry_date, entry_price = r.date, buy
                else:
                    entry_price = (grams * entry_price + qty * buy) / (grams + qty)
                cash -= qty*buy; grams += qty
                trades.append({"date":str(r.date.date()),"action":"BUY","grams":qty,"price":buy})
        elif desired < current-100 or (target == 0 and grams > 1e-10):
            qty = min(grams, (current-desired)/sell)
            cash += qty*sell; grams -= qty
            trades.append({"date":str(r.date.date()),"action":"SELL","grams":qty,"price":sell,"reason":exit_reason or "target_rebalance"})
        equity = cash+grams*(r.close-half)
        records.append({"date":r.date,"equity":equity,"cash":cash,"grams":grams,
                        "target":target,"close":r.close,"halted":halted})
    curve = pd.DataFrame(records)
    ret = curve.equity.pct_change().fillna(0)
    years = max((curve.date.iloc[-1]-curve.date.iloc[0]).days/365.25,1/365.25)
    peak = curve.equity.cummax().clip(lower=initial)
    drawdown = curve.equity/peak-1
    annvol = float(ret.std(ddof=0)*np.sqrt(252))
    metrics = {"bars":len(curve),"start":str(curve.date.iloc[0].date()),
               "end":str(curve.date.iloc[-1].date()),"initial_cny":initial,
               "final_cny":round(float(curve.equity.iloc[-1]),2),
               "total_return":round(float(curve.equity.iloc[-1]/initial-1),6),
               "cagr":round(float((curve.equity.iloc[-1]/initial)**(1/years)-1),6),
               "max_drawdown":round(float(drawdown.min()),6),
               "annual_volatility":round(annvol,6),
               "sharpe_rf0":round(float(ret.mean()*252/annvol),6) if annvol else None,
               "trade_count":len(trades),"halted":halted,
               "max_holding_days":max_holding_days,"take_profit":take_profit,
               "stop_loss":stop_loss,"exit_reasons":exit_reasons,
               "proxy_spread_cny_per_gram":spread_per_gram,
               "data_type":"Au99.99 daily market proxy; NOT bank minute quotes",
               "execution":"signal close, earliest next session open"}
    return curve, pd.DataFrame(trades), metrics

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",default=None)
    p.add_argument("--out",default="artifacts/gold_backtest")
    args=p.parse_args()
    df=load_data(args.csv)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    df.to_csv(out/"au9999_daily.csv",index=False)
    curve,trades,metrics=backtest(df)
    curve.to_csv(out/"equity_curve.csv",index=False)
    trades.to_csv(out/"trades.csv",index=False)
    (out/"metrics.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
