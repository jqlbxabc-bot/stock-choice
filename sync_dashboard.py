#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本地选股/成交结果整理为 dashboard/data.json。
默认只写本地文件，不自动下单，也不自动推送 GitHub。
如需同步云端，可由你自己的 git/定时任务执行 commit + push。
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output"
DASH = BASE / "dashboard"
DATA = DASH / "data.json"

MAX_CANDIDATES = 5
FRESH_MINUTES = 20

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
    return str(x.get("股票名称") or x.get("名称") or x.get("name") or x.get("代码") or "未知")

def score(x):
    for k in ("综合评分","评分","score","总分"):
        try:
            return float(x.get(k))
        except (TypeError, ValueError):
            pass
    return 0.0

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

    actions = []
    if fresh:
        for x in rows:
            actions.append({
                "stock": stock_name(x),
                "state": "继续盯",
                "trigger": "需结合板块同步、关键位与盘中确认",
                "invalidate": "数据过期 / 板块转弱 / 触发个人风控",
            })

    # 总开关：灰灯=无新鲜数据；红灯=明确风控触发；黄灯=可观察但需确认；绿灯暂不自动给出。
    if not fresh:
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
        "data_freshness": "新鲜" if fresh else "过期或缺失",
        "trade_gate": trade_gate,
        "gate_note": gate_note,
        "market_state": market_state,
        "market_note": market_note,
        "holding_risk_count": None,
        "week_violations": None,
        "loss_streak": None,
        "experiment_done": 0,
        "experiment_total": 20,
        "actions": actions,
    }
    DASH.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"updated: {DATA}")
    print(f"gate={trade_gate}, candidates={len(actions)}, freshness={payload['data_freshness']}")

if __name__ == "__main__":
    build()
