#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本地选股/成交结果整理为 dashboard/data.json 与 docs/data.json。
默认不自动下单；云端发布由 git push 触发。
"""

from __future__ import annotations
import csv
import json
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

def latest_json():
    if not OUTPUT.exists():
        return None
    files = sorted(
        [p for p in OUTPUT.glob("*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None

def load_list(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def stock_name(x):
    return str(x.get("股票名称") or x.get("名称") or x.get("name") or x.get("代码") or x.get("stock_name") or "未知")

def score(x):
    for k in ("综合评分","评分","score","总分"):
        try:
            return float(x.get(k))
        except (TypeError, ValueError):
            pass
    return 0.0

def latest_trade_file():
    found = [p for p in TRADE_CANDIDATES if p.exists()]
    return max(found, key=lambda p:p.stat().st_mtime) if found else None

def load_csv(path):
    if not path:
        return []
    for enc in ("utf-8-sig","utf-8","gbk"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            pass
    return []

def truthy(v):
    return str(v).strip().lower() in {"1","true","yes","y","是","违规"}

def trade_metrics(rows):
    if not rows:
        return {
            "experiment_done":0,
            "week_violations":None,
            "holding_risk_count":None,
            "loss_streak":None,
            "guardrail_red":False,
        }

    # 兼容统一模板中的常见字段；缺失字段时不猜。
    experiment_done = min(len(rows), EXPERIMENT_TOTAL)

    violations = 0
    holding_risk = 0
    guardrail_red = False
    pnl_seq = []

    for r in rows[-200:]:
        violation = (
            truthy(r.get("是否违规"))
            or bool(str(r.get("violation_type") or "").strip())
            or str(r.get("behavior_risk_state") or "").strip() in {"B3","B4"}
        )
        if violation:
            violations += 1

        try:
            buy_count = int(float(r.get("buy_count_in_round") or r.get("买入次数") or 0))
        except Exception:
            buy_count = 0
        below_cost_add = truthy(r.get("below_cost_add")) or truthy(r.get("亏损补仓"))
        try:
            holding_days = int(float(r.get("holding_days") or r.get("持有天数") or 0))
        except Exception:
            holding_days = 0

        if below_cost_add or buy_count >= 3 or holding_days >= 4:
            holding_risk += 1
        if below_cost_add or buy_count >= 3:
            guardrail_red = True

        raw_pnl = r.get("pnl_pct") or r.get("盈亏%") or r.get("收益率")
        if raw_pnl not in (None,""):
            try:
                pnl_seq.append(float(str(raw_pnl).replace("%","")))
            except Exception:
                pass

    loss_streak = 0
    for p in reversed(pnl_seq):
        if p < 0:
            loss_streak += 1
        else:
            break

    if loss_streak >= 2:
        guardrail_red = True

    return {
        "experiment_done":experiment_done,
        "week_violations":violations,
        "holding_risk_count":holding_risk,
        "loss_streak":loss_streak if pnl_seq else None,
        "guardrail_red":guardrail_red,
    }

def write_payload(payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    for folder in (DASH, DOCS):
        folder.mkdir(exist_ok=True)
        (folder / "data.json").write_text(text, encoding="utf-8")

def build():
    now = datetime.now()
    latest = latest_json()
    fresh = False
    rows = []
    source_time = None

    if latest:
        source_time = datetime.fromtimestamp(latest.stat().st_mtime)
        fresh = (now - source_time) <= timedelta(minutes=FRESH_MINUTES)
        rows = load_list(latest)

    rows = sorted(rows, key=score, reverse=True)[:MAX_CANDIDATES]

    trade_file = latest_trade_file()
    trades = load_csv(trade_file)
    metrics = trade_metrics(trades)

    actions = []
    if fresh and not metrics["guardrail_red"]:
        for x in rows:
            actions.append({
                "stock": stock_name(x),
                "state": "继续盯",
                "trigger": "需结合板块同步、关键位与盘中确认",
                "invalidate": "数据过期 / 板块转弱 / 触发个人风控",
            })

    if metrics["guardrail_red"]:
        trade_gate = "红灯"
        gate_note = "个人风控已触发：停止新增交易，先复核行为与风险"
        market_state = "M1" if fresh else "M0"
        market_note = "即使候选有效，也不覆盖个人风控"
    elif not fresh:
        trade_gate = "灰灯"
        gate_note = "数据不新鲜：只复盘，不生成交易型动作"
        market_state = "M0"
        market_note = "未载入当日有效市场数据"
    else:
        trade_gate = "黄灯"
        gate_note = "数据有效，但仍需板块/关键位/个人规则确认"
        market_state = "M2"
        market_note = "候选仅供观察，不代表买入指令"

    payload = {
        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source_time": source_time.strftime("%Y-%m-%d %H:%M:%S") if source_time else None,
        "trade_source_time": datetime.fromtimestamp(trade_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if trade_file else None,
        "data_freshness": "新鲜" if fresh else "过期或缺失",
        "trade_gate": trade_gate,
        "gate_note": gate_note,
        "market_state": market_state,
        "market_note": market_note,
        "holding_risk_count": metrics["holding_risk_count"],
        "week_violations": metrics["week_violations"],
        "loss_streak": metrics["loss_streak"],
        "experiment_done": metrics["experiment_done"],
        "experiment_total": EXPERIMENT_TOTAL,
        "actions": actions,
    }
    write_payload(payload)
    print("updated: dashboard/data.json + docs/data.json")
    print(f"gate={trade_gate}, candidates={len(actions)}, freshness={payload['data_freshness']}")

if __name__ == "__main__":
    build()
