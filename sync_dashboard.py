#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本地选股、持仓、成交和信号结果整理为 dashboard/data.json 与 docs/data.json。
默认不自动下单；云端发布由 git push 触发。
"""

from __future__ import annotations
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
DASH = BASE / "dashboard"
DOCS = BASE / "docs"
EXPORTS = BASE / "exports"

MAX_CANDIDATES = 5
FRESH_MINUTES = 20
EXPERIMENT_TOTAL = 20

TRADE_CANDIDATES = [
    EXPORTS / "latest_normalized_trades.csv",
    EXPORTS / "trades.csv",
    BASE / "latest_normalized_trades.csv",
]
HOLDING_CANDIDATES = [
    EXPORTS / "current_positions.csv",
    EXPORTS / "holdings.csv",
    EXPORTS / "positions.csv",
    BASE / "current_positions.csv",
]
SIGNAL_CANDIDATES = [
    EXPORTS / "signal_outcomes.csv",
    BASE / "signal_outcomes.csv",
]

def first_existing(candidates):
    found=[p for p in candidates if p.exists()]
    return max(found,key=lambda p:p.stat().st_mtime) if found else None

def latest_json():
    if not OUTPUT.exists():
        return None
    files=sorted([p for p in OUTPUT.glob("*.json") if p.is_file()],key=lambda p:p.stat().st_mtime,reverse=True)
    return files[0] if files else None

def load_list(path):
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data,list) else []
    except Exception:
        return []

def load_csv(path):
    if not path:
        return []
    for enc in ("utf-8-sig","utf-8","gbk"):
        try:
            with path.open("r",encoding=enc,newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            pass
    return []

def stock_name(x):
    return str(x.get("股票名称") or x.get("名称") or x.get("name") or x.get("证券名称") or x.get("代码") or x.get("stock_name") or "未知")

def stock_code(x):
    return str(x.get("股票代码") or x.get("证券代码") or x.get("代码") or x.get("stock_code") or x.get("code") or "")

def num(v):
    if v in (None,""):
        return None
    try:
        return float(str(v).replace(",","").replace("%","").strip())
    except Exception:
        return None

def intval(v):
    n=num(v)
    return int(n) if n is not None else 0

def truthy(v):
    return str(v).strip().lower() in {"1","true","yes","y","是","违规"}

def score(x):
    for k in ("综合评分","评分","score","总分"):
        n=num(x.get(k))
        if n is not None:
            return n
    return 0.0

def trade_metrics(rows):
    if not rows:
        return {"experiment_done":0,"week_violations":None,"holding_risk_count":None,"loss_streak":None,"guardrail_red":False,"daily_pnl":[],"weekly_pnl":[]}

    violations=0
    holding_risk=0
    guardrail_red=False
    pnl_seq=[]
    daily=defaultdict(float)
    daily_seen=set()

    for r in rows[-500:]:
        violation=(truthy(r.get("是否违规")) or bool(str(r.get("violation_type") or "").strip()) or str(r.get("behavior_risk_state") or "").strip() in {"B3","B4"})
        if violation:
            violations+=1

        buy_count=intval(r.get("buy_count_in_round") or r.get("买入次数"))
        below_cost_add=truthy(r.get("below_cost_add")) or truthy(r.get("亏损补仓"))
        holding_days=intval(r.get("holding_days") or r.get("持有天数"))

        if below_cost_add or buy_count>=3 or holding_days>=4:
            holding_risk+=1
        if below_cost_add or buy_count>=3:
            guardrail_red=True

        rp=r.get("pnl_pct") or r.get("盈亏%") or r.get("收益率")
        p=num(rp)
        if p is not None:
            pnl_seq.append(p)

        date=str(r.get("date") or r.get("日期") or r.get("成交日期") or r.get("trade_date") or "")[:10]
        cash=num(r.get("fifo_pnl") or r.get("盈亏金额") or r.get("净盈亏") or r.get("pnl"))
        if date and cash is not None:
            daily[date]+=cash
            daily_seen.add(date)

    loss_streak=0
    for p in reversed(pnl_seq):
        if p<0: loss_streak+=1
        else: break
    if loss_streak>=2:
        guardrail_red=True

    daily_items=[{"date":d,"pnl":round(daily[d],2)} for d in sorted(daily_seen)[-30:]]
    weekly=defaultdict(float)
    for d,v in daily.items():
        try:
            dt=datetime.strptime(d,"%Y-%m-%d")
            y,w,_=dt.isocalendar()
            weekly[f"{y}-W{w:02d}"]+=v
        except Exception:
            pass
    weekly_items=[{"week":k,"pnl":round(weekly[k],2)} for k in sorted(weekly.keys())[-12:]]

    return {
        "experiment_done":min(len(rows),EXPERIMENT_TOTAL),
        "week_violations":violations,
        "holding_risk_count":holding_risk,
        "loss_streak":loss_streak if pnl_seq else None,
        "guardrail_red":guardrail_red,
        "daily_pnl":daily_items,
        "weekly_pnl":weekly_items,
    }

def holdings_view(rows):
    out=[]
    for r in rows[:50]:
        qty=num(r.get("数量") or r.get("持仓数量") or r.get("qty") or r.get("quantity"))
        cost=num(r.get("成本价") or r.get("成本") or r.get("cost_price"))
        price=num(r.get("现价") or r.get("最新价") or r.get("price") or r.get("last_price"))
        pnl_pct=num(r.get("盈亏%") or r.get("收益率") or r.get("pnl_pct"))
        if pnl_pct is None and cost not in (None,0) and price is not None:
            pnl_pct=(price/cost-1)*100
        buy_count=intval(r.get("买入次数") or r.get("buy_count_in_round"))
        holding_days=intval(r.get("持有天数") or r.get("holding_days"))
        below=truthy(r.get("亏损补仓")) or truthy(r.get("below_cost_add"))
        risks=[]
        if below: risks.append("亏损补仓")
        if buy_count>=3: risks.append("第3次及以后买入")
        if holding_days>=4: risks.append("持仓≥4天待复核")
        out.append({
            "stock":stock_name(r),
            "code":stock_code(r),
            "qty":qty,
            "cost":cost,
            "price":price,
            "pnl_pct":round(pnl_pct,2) if pnl_pct is not None else None,
            "risk":" / ".join(risks) if risks else "正常",
        })
    return out[:20]

def signal_stats(rows):
    def collect(keys):
        vals=[]
        for r in rows:
            for k in keys:
                v=num(r.get(k))
                if v is not None:
                    vals.append(v); break
        if not vals:
            return {"samples":0,"avg_return":None,"win_rate":None}
        return {
            "samples":len(vals),
            "avg_return":round(sum(vals)/len(vals),2),
            "win_rate":round(sum(1 for x in vals if x>0)/len(vals)*100,1),
        }
    return {
        "d1":collect(["return_1d","1日收益","1d_return"]),
        "d3":collect(["return_3d","3日收益","3d_return"]),
        "d5":collect(["return_5d","5日收益","5d_return"]),
    }


def row_pnl_pct(r):
    return num(r.get("pnl_pct") or r.get("盈亏%") or r.get("收益率"))

def row_cash_pnl(r):
    return num(r.get("fifo_pnl") or r.get("盈亏金额") or r.get("净盈亏") or r.get("pnl"))

def behavior_flags(r):
    flags=[]
    buy_count=intval(r.get("buy_count_in_round") or r.get("买入次数"))
    holding_days=intval(r.get("holding_days") or r.get("持有天数"))
    below=truthy(r.get("below_cost_add")) or truthy(r.get("亏损补仓"))
    if below: flags.append("亏损后补仓")
    if buy_count>=3: flags.append("第3次及以后买入")
    if holding_days>=4: flags.append("持仓≥4天未复核")
    if truthy(r.get("是否违规")) or bool(str(r.get("violation_type") or "").strip()) or str(r.get("behavior_risk_state") or "") in {"B3","B4"}:
        flags.append("违反既定规则")
    planned=num(r.get("planned_position_pct") or r.get("计划仓位%"))
    actual=num(r.get("actual_position_pct") or r.get("实际仓位%"))
    if planned is not None and actual is not None and actual>planned+0.01:
        flags.append("实际仓位超计划")
    return list(dict.fromkeys(flags))

def behavior_ranking(rows):
    buckets={}
    for r in rows[-500:]:
        cash=row_cash_pnl(r)
        pp=row_pnl_pct(r)
        for flag in behavior_flags(r):
            b=buckets.setdefault(flag,{"behavior":flag,"count":0,"cash_pnl":0.0,"cash_samples":0,"pct_sum":0.0,"pct_samples":0})
            b["count"]+=1
            if cash is not None:
                b["cash_pnl"]+=cash; b["cash_samples"]+=1
            if pp is not None:
                b["pct_sum"]+=pp; b["pct_samples"]+=1
    out=[]
    for b in buckets.values():
        out.append({
            "behavior":b["behavior"],
            "count":b["count"],
            "cash_pnl":round(b["cash_pnl"],2) if b["cash_samples"] else None,
            "avg_pnl_pct":round(b["pct_sum"]/b["pct_samples"],2) if b["pct_samples"] else None,
            "cash_samples":b["cash_samples"],
        })
    out.sort(key=lambda x:(x["cash_pnl"] if x["cash_pnl"] is not None else 10**18,-x["count"]))
    return out[:6]

def execution_score(r):
    s=100
    flags=behavior_flags(r)
    if "亏损后补仓" in flags: s-=40
    if "第3次及以后买入" in flags: s-=25
    if "持仓≥4天未复核" in flags: s-=15
    if "违反既定规则" in flags: s-=25
    if "实际仓位超计划" in flags: s-=10
    explicit=str(r.get("rule_satisfied") or r.get("买入前规则是否满足") or "").strip().lower()
    if explicit in {"false","0","否","不满足"}: s-=20
    return max(0,min(100,s)),flags

def execution_quality(rows):
    out=[]
    for r in rows[-20:]:
        s,flags=execution_score(r)
        pnl=row_pnl_pct(r)
        if s>=85: grade="A"
        elif s>=70: grade="B"
        elif s>=55: grade="C"
        else: grade="D"
        if pnl is not None and pnl<0 and s>=80:
            kind="好交易但亏钱"
        elif pnl is not None and pnl>0 and s<60:
            kind="坏交易碰巧赚钱"
        elif pnl is None:
            kind="待结果"
        else:
            kind="过程与结果一致"
        out.append({
            "date":str(r.get("date") or r.get("日期") or r.get("成交日期") or r.get("trade_date") or "")[:10],
            "stock":stock_name(r),
            "code":stock_code(r),
            "score":s,
            "grade":grade,
            "pnl_pct":round(pnl,2) if pnl is not None else None,
            "classification":kind,
            "issues":" / ".join(flags) if flags else "无明确违规",
        })
    return list(reversed(out))

def write_payload(payload):
    text=json.dumps(payload,ensure_ascii=False,indent=2)
    for folder in (DASH,DOCS):
        folder.mkdir(exist_ok=True)
        (folder/"data.json").write_text(text,encoding="utf-8")

def build():
    now=datetime.now()
    latest=latest_json()
    fresh=False
    rows=[]
    source_time=None

    if latest:
        source_time=datetime.fromtimestamp(latest.stat().st_mtime)
        fresh=(now-source_time)<=timedelta(minutes=FRESH_MINUTES)
        rows=load_list(latest)

    rows=sorted(rows,key=score,reverse=True)[:MAX_CANDIDATES]

    trade_file=first_existing(TRADE_CANDIDATES)
    holding_file=first_existing(HOLDING_CANDIDATES)
    signal_file=first_existing(SIGNAL_CANDIDATES)

    trades=load_csv(trade_file)
    holdings=holdings_view(load_csv(holding_file))
    sigstats=signal_stats(load_csv(signal_file))
    metrics=trade_metrics(trades)

    actions=[]
    if fresh and not metrics["guardrail_red"]:
        for x in rows:
            actions.append({
                "stock":stock_name(x),
                "state":"继续盯",
                "trigger":"需结合板块同步、关键位与盘中确认",
                "invalidate":"数据过期 / 板块转弱 / 触发个人风控",
            })

    if metrics["guardrail_red"]:
        trade_gate="红灯"
        gate_note="个人风控已触发：停止新增交易，先复核行为与风险"
        market_state="M1" if fresh else "M0"
        market_note="即使候选有效，也不覆盖个人风控"
    elif not fresh:
        trade_gate="灰灯"
        gate_note="数据不新鲜：只复盘，不生成交易型动作"
        market_state="M0"
        market_note="未载入当日有效市场数据"
    else:
        trade_gate="黄灯"
        gate_note="数据有效，但仍需板块/关键位/个人规则确认"
        market_state="M2"
        market_note="候选仅供观察，不代表买入指令"

    payload={
        "updated_at":now.strftime("%Y-%m-%d %H:%M:%S"),
        "source_time":source_time.strftime("%Y-%m-%d %H:%M:%S") if source_time else None,
        "trade_source_time":datetime.fromtimestamp(trade_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if trade_file else None,
        "holding_source_time":datetime.fromtimestamp(holding_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if holding_file else None,
        "signal_source_time":datetime.fromtimestamp(signal_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if signal_file else None,
        "data_freshness":"新鲜" if fresh else "过期或缺失",
        "trade_gate":trade_gate,
        "gate_note":gate_note,
        "market_state":market_state,
        "market_note":market_note,
        "holding_risk_count":metrics["holding_risk_count"],
        "week_violations":metrics["week_violations"],
        "loss_streak":metrics["loss_streak"],
        "experiment_done":metrics["experiment_done"],
        "experiment_total":EXPERIMENT_TOTAL,
        "actions":actions,
        "holdings":holdings,
        "signal_stats":sigstats,
        "daily_pnl":metrics["daily_pnl"],
        "weekly_pnl":metrics["weekly_pnl"],
        "behavior_ranking":behavior_ranking(trades),
        "execution_quality":execution_quality(trades),
    }
    write_payload(payload)
    print("updated: dashboard/data.json + docs/data.json")
    print(f"gate={trade_gate}, candidates={len(actions)}, holdings={len(holdings)}, freshness={payload['data_freshness']}")

if __name__=="__main__":
    build()
