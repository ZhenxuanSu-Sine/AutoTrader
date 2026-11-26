"""Secretary-rule gold strategy. Real SGE daily bars, proxy execution only.

Observation and decisions use only current/prior session OPEN values. A forced
last-day order uses that day's open; no daily close/high/low is used to trade.
This is not a bank-minute or guaranteed executable price backtest.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.backtest_gold_daily import load_data


def secretary_backtest(df, buy_window=30, sell_window=30, buy_fraction=.37,
                       sell_fraction=.37, spread_per_gram=3.8, initial=20000.,
                       max_weight=.8, stop_loss=None, take_profit=None):
    for w in (buy_window, sell_window):
        if not isinstance(w, int) or w < 2:
            raise ValueError("windows must be integers >= 2")
    for f in (buy_fraction, sell_fraction):
        if not 0 < f < 1:
            raise ValueError("observation fractions must lie in (0,1)")
    if spread_per_gram < 0 or not 0 < max_weight <= 1:
        raise ValueError("invalid spread or weight")
    for v in (stop_loss, take_profit):
        if v is not None and not 0 < v < 1:
            raise ValueError("stop_loss/take_profit must lie in (0,1)")
    df = df.sort_values("date").reset_index(drop=True)
    if df.empty:
        raise ValueError("empty data")
    cash, grams, halted = float(initial), 0., False
    phase, start, entry = "buy", 0, None
    observations, trades, curve = [], [], []
    pending = None
    half = spread_per_gram / 2
    for i, r in enumerate(df.itertuples(index=False)):
        op, cl = float(r.open), float(r.close)
        ask, bid = op + half, op - half
        if bid <= 0 or cl - half <= 0:
            raise ValueError("spread exceeds market price")
        equity_open = cash + grams * bid
        loss = 1 - equity_open / initial
        action, reason = None, None
        if loss >= .25:
            halted = True
        if grams > 0 and (halted or loss >= .20):
            action, reason = "SELL", "account_risk"
        elif grams > 0 and entry is not None:
            pnl = bid / entry - 1
            if stop_loss is not None and pnl <= -stop_loss:
                action, reason = "SELL", "stop_loss"
            elif take_profit is not None and pnl >= take_profit:
                action, reason = "SELL", "take_profit"
        # A current-session open can only trigger a NEXT-session fill.
        if action is None and not halted and pending is not None:
            action, reason = pending
        pending = None
        if action == "BUY" and grams == 0:
            # Account warning: cap exposure at 25% of equity.
            weight = min(max_weight, .25) if loss >= .15 else max_weight
            qty = max(0., min(cash / ask, equity_open * weight / ask))
            if qty > 0:
                cash -= qty * ask
                grams += qty
                entry = ask
                trades.append({"date":str(r.date.date()),"action":"BUY",
                               "grams":qty,"price":ask,"reason":reason})
                phase, start, observations = "sell", i+1, []
        elif action == "SELL" and grams > 0:
            trades.append({"date":str(r.date.date()),"action":"SELL",
                           "grams":grams,"price":bid,"reason":reason})
            cash += grams * bid
            grams, entry = 0., None
            phase, start, observations = "buy", i+1, []
        if i >= start and not halted:
            w = buy_window if phase == "buy" else sell_window
            f = buy_fraction if phase == "buy" else sell_fraction
            elapsed = i - start
            k = max(1, min(w-1, math.ceil(w*f)))
            if elapsed >= k:
                ref = min(observations) if phase == "buy" else max(observations)
                is_record = op < ref if phase == "buy" else op > ref
                if is_record:
                    pending = ("BUY" if phase == "buy" else "SELL", "record")
            if pending is None and elapsed == w-2:
                pending = ("BUY" if phase == "buy" else "SELL", "window_expiry")
            observations.append(op)
        curve.append({"date":r.date,"equity":cash + grams*(cl-half),
                      "cash":cash,"grams":grams,"phase":phase,"halted":halted})
    curve = pd.DataFrame(curve)
    trades = pd.DataFrame(trades,columns=["date","action","grams","price","reason"])
    ret = curve.equity.pct_change()
    ret.iloc[0] = curve.equity.iloc[0] / initial - 1
    years = max((curve.date.iloc[-1]-curve.date.iloc[0]).days/365.25,1/365.25)
    dd = curve.equity / curve.equity.cummax().clip(lower=initial)-1
    vol = float(ret.std(ddof=0)*np.sqrt(252))
    metrics = {"bars":len(curve),"start":str(curve.date.iloc[0].date()),
               "end":str(curve.date.iloc[-1].date()),
               "final_cny":round(float(curve.equity.iloc[-1]),2),
               "total_return":round(float(curve.equity.iloc[-1]/initial-1),6),
               "cagr":round(float((curve.equity.iloc[-1]/initial)**(1/years)-1),6),
               "max_drawdown":round(float(dd.min()),6),
               "sharpe_rf0":round(float(ret.mean()*252/vol),6) if vol else None,
               "trade_count":len(trades),"buy_window":buy_window,
               "sell_window":sell_window,"buy_fraction":buy_fraction,
               "sell_fraction":sell_fraction,"stop_loss":stop_loss,
               "take_profit":take_profit,"halted":halted,
               "spread_per_gram":spread_per_gram,
               "data_type":"SGE Au99.99 daily proxy; NOT verified bank minute quotes",
               "execution":"observe open; next-session fill; expiry decision penultimate session to ensure final-window open exit"}
    return curve, trades, metrics


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv")
    p.add_argument("--out",default="artifacts/gold_secretary")
    p.add_argument("--buy-window",type=int,default=30)
    p.add_argument("--sell-window",type=int,default=30)
    p.add_argument("--stop-loss",type=float)
    p.add_argument("--take-profit",type=float)
    args=p.parse_args()
    df=load_data(args.csv)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    df.to_csv(out/"au9999_daily.csv",index=False)
    # Joint 8x8 scan: buy and sell observation fractions are independent.
    fractions=(.1,.2,.3,.37,.4,.5,.6,.7)
    results=[]
    # Fixed chronological split; no parameter selection using the test period.
    split=max(70,int(len(df)*.7))
    train=df.iloc[:split].copy()
    test=df.iloc[split:].copy()
    if len(test)<60:
        raise ValueError("at least 60 held-out bars required for validation")
    for buy_f in fractions:
        for sell_f in fractions:
            _,_,train_m=secretary_backtest(
                train,buy_window=args.buy_window,sell_window=args.sell_window,
                buy_fraction=buy_f,sell_fraction=sell_f,
                stop_loss=args.stop_loss,take_profit=args.take_profit)
            _,_,test_m=secretary_backtest(
                test,buy_window=args.buy_window,sell_window=args.sell_window,
                buy_fraction=buy_f,sell_fraction=sell_f,
                stop_loss=args.stop_loss,take_profit=args.take_profit)
            results.append({
                "buy_fraction":buy_f,"sell_fraction":sell_f,
                "train_total_return":train_m["total_return"],
                "train_max_drawdown":train_m["max_drawdown"],
                "train_sharpe_rf0":train_m["sharpe_rf0"],
                "train_trade_count":train_m["trade_count"],
                "test_total_return":test_m["total_return"],
                "test_max_drawdown":test_m["max_drawdown"],
                "test_sharpe_rf0":test_m["sharpe_rf0"],
                "test_trade_count":test_m["trade_count"]})
    table=pd.DataFrame(results)
    table.to_csv(out/"fraction_grid_64_train_test.csv",index=False)
    # Select by train-only Sharpe; report holdout without further tuning.
    ranked=table.sort_values("train_sharpe_rf0",ascending=False,na_position="last")
    chosen=ranked.iloc[0]
    chosen_pair=(float(chosen.buy_fraction),float(chosen.sell_fraction))
    baseline_pair=(.37,.37)
    report={"train_end":str(train.date.iloc[-1].date()),
            "test_start":str(test.date.iloc[0].date()),
            "selection_metric":"train_sharpe_rf0",
            "selected_buy_fraction":chosen_pair[0],
            "selected_sell_fraction":chosen_pair[1],
            "selected_train_metrics":{k:float(v) for k,v in chosen[["train_total_return","train_max_drawdown","train_sharpe_rf0","train_trade_count"]].items()},
            "selected_heldout_metrics":{k:float(v) for k,v in chosen[["test_total_return","test_max_drawdown","test_sharpe_rf0","test_trade_count"]].items()},
            "note":"Holdout starts flat and may have a different exposure than a continuous live strategy; no bank quote validation."}
    for label,pair in (("classic37",baseline_pair),("selected",chosen_pair)):
        curve,trades,m=secretary_backtest(
            df,buy_window=args.buy_window,sell_window=args.sell_window,
            buy_fraction=pair[0],sell_fraction=pair[1],
            stop_loss=args.stop_loss,take_profit=args.take_profit)
        curve.to_csv(out/f"equity_curve_{label}.csv",index=False)
        trades.to_csv(out/f"trades_{label}.csv",index=False)
        report[f"full_sample_{label}"]=m
    (out/"scan_report.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
