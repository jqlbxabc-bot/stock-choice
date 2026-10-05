#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘中实时选股循环：实时快照 -> 自适应多因子 -> 前5 -> 最新结果文件。"""

from __future__ import annotations
import datetime
import json
import os
import time
from pathlib import Path

from main import DynamicStockSelector, is_market_open

BASE = Path(__file__).resolve().parent
EXPORTS = BASE / "exports"
EXPORTS.mkdir(exist_ok=True)
LATEST = EXPORTS / "latest_realtime_candidates.json"
STATUS = EXPORTS / "realtime_status.json"

def normalize_code(x):
    return str(x.get("代码") or x.get("code") or "")

def compact(items):
    return [
        {
            "代码": x.get("代码"),
            "名称": x.get("名称"),
            "最新价": x.get("最新价"),
            "涨跌幅": x.get("涨跌幅"),
            "评分": x.get("评分"),
            "市场状态": x.get("市场状态"),
            "5日强度": x.get("5日强度"),
            "20日强度": x.get("20日强度"),
            "60日强度": x.get("60日强度"),
            "ATR%": x.get("ATR%"),
            "量能比": x.get("量能比"),
            "20日位置": x.get("20日位置"),
            "选择时间": x.get("选择时间"),
            "策略": x.get("策略"),
        }
        for x in items
    ]

def signature(items):
    return [(normalize_code(x), round(float(x.get("评分") or 0), 1)) for x in items]

def write_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def run_once(selector):
    selector.stock_data = None
    df = selector.get_stock_data()
    if df is None or df.empty:
        raise RuntimeError("实时行情获取失败")
    result = selector.run_strategy("adaptive_multifactor", round_num=1)
    return compact(result)

def main():
    selector = DynamicStockSelector()
    rt = selector.config.get("realtime", {})
    interval = max(15, int(rt.get("refresh_seconds", 30)))
    market_only = bool(rt.get("market_only", True))
    max_candidates = max(1, int(rt.get("max_candidates", 5)))
    previous = None

    print("=" * 60)
    print("A股实时选股模式")
    print(f"刷新间隔: {interval} 秒；候选上限: {max_candidates}")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    while True:
        now = datetime.datetime.now()
        try:
            if market_only and not is_market_open(now, selector.config):
                status = {
                    "running": True,
                    "market_open": False,
                    "last_check": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "message": "非交易时段，等待开盘",
                }
                write_json(STATUS, status)
                print(f"[{status['last_check']}] 非交易时段")
            else:
                result = run_once(selector)[:max_candidates]
                sig = signature(result)
                changed = sig != previous
                if changed or not LATEST.exists():
                    payload = {
                        "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "akshare_realtime",
                        "strategy": "adaptive_multifactor",
                        "candidates": result,
                    }
                    write_json(LATEST, payload)
                    previous = sig
                    print(f"[{payload['updated_at']}] 候选变化，已更新 {len(result)} 只")
                    for i, x in enumerate(result, 1):
                        print(f"  {i}. {x.get('代码')} {x.get('名称')} 评分={float(x.get('评分') or 0):.1f}")
                else:
                    print(f"[{now:%H:%M:%S}] 候选无明显变化")

                write_json(STATUS, {
                    "running": True,
                    "market_open": True,
                    "last_check": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "candidate_count": len(result),
                    "message": "实时选股正常",
                })
        except KeyboardInterrupt:
            print("\n实时选股已停止")
            break
        except Exception as exc:
            write_json(STATUS, {
                "running": True,
                "market_open": is_market_open(now, selector.config),
                "last_check": now.strftime("%Y-%m-%d %H:%M:%S"),
                "message": f"本轮失败: {exc}",
            })
            print(f"[{now:%H:%M:%S}] 本轮失败: {exc}")

        time.sleep(interval)

if __name__ == "__main__":
    main()
