#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态选股系统 - Web界面
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import DynamicStockSelector

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

selector = DynamicStockSelector()


def api_success(**payload):
    payload["success"] = True
    return jsonify(payload)


def api_error(message: str, status_code: int = 200):
    return jsonify({"success": False, "error": message}), status_code


def selection_file_path(filename: str) -> str | None:
    """只允许读取 output 目录下的 JSON 文件。"""
    if not filename or filename != os.path.basename(filename) or not filename.endswith(".json"):
        return None

    output_root = os.path.abspath(OUTPUT_DIR)
    filepath = os.path.abspath(os.path.join(output_root, filename))
    if os.path.commonpath([output_root, filepath]) != output_root:
        return None
    return filepath


def list_selection_files() -> list[dict]:
    files = []
    if not os.path.exists(OUTPUT_DIR):
        return files

    for filename in os.listdir(OUTPUT_DIR):
        filepath = selection_file_path(filename)
        if filepath is None or not os.path.isfile(filepath):
            continue

        stat = os.stat(filepath)
        files.append(
            {
                "filename": filename,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "mtime": stat.st_mtime,
            }
        )

    files.sort(key=lambda item: item["mtime"], reverse=True)
    return files


@app.route("/")
def index():
    """主页。"""
    return render_template("index.html")


@app.route("/api/strategies")
def get_strategies():
    """获取可用策略列表。"""
    try:
        return api_success(strategies=selector.get_available_strategies())
    except Exception as exc:
        return api_error(str(exc))


@app.route("/api/run_strategy", methods=["POST"])
def run_strategy():
    """运行指定策略。"""
    try:
        data = request.get_json(silent=True) or {}
        strategy_id = data.get("strategy_id")

        if not strategy_id:
            return api_error("未指定策略ID", 400)

        if selector.stock_data is None:
            selector.get_stock_data()

        if selector.stock_data is None:
            return api_error("无法获取股票数据")

        result = selector.run_strategy(strategy_id, round_num=1)
        if not result:
            return api_error("未找到符合条件的股票")

        strategy_name = next(
            (strategy["name"] for strategy in selector.get_available_strategies() if strategy["id"] == strategy_id),
            strategy_id,
        )
        selector.save_selection(result, strategy_name)
        return api_success(result=result, count=len(result), strategy=strategy_name)
    except Exception as exc:
        return api_error(str(exc))


@app.route("/api/selections")
def get_selections():
    """获取选股结果列表。"""
    try:
        files = list_selection_files()
        for item in files:
            item.pop("mtime", None)
        return api_success(files=files)
    except Exception as exc:
        return api_error(str(exc))


@app.route("/api/selection/<filename>")
def get_selection_detail(filename):
    """获取选股结果详情。"""
    try:
        filepath = selection_file_path(filename)
        if filepath is None or not os.path.exists(filepath):
            return api_error("文件不存在", 404)

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return api_success(data=data)
    except Exception as exc:
        return api_error(str(exc))


@app.route("/api/latest")
def get_latest_selection():
    """获取最新的选股结果。"""
    try:
        files = list_selection_files()
        if not files:
            return api_error("没有选股结果")

        latest_file = files[0]
        filepath = selection_file_path(latest_file["filename"])
        if filepath is None:
            return api_error("最新文件路径异常")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        return api_success(filename=latest_file["filename"], data=data)
    except Exception as exc:
        return api_error(str(exc))


@app.route("/api/statistics")
def get_statistics():
    """获取统计信息。"""
    try:
        stats = {
            "total_files": 0,
            "total_selections": 0,
            "latest_update": None,
            "strategies": {},
        }

        files = list_selection_files()
        stats["total_files"] = len(files)
        if files:
            stats["latest_update"] = files[0]["modified"]

        for item in files:
            filepath = selection_file_path(item["filename"])
            if filepath is None:
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(data, list):
                continue

            stats["total_selections"] += len(data)
            for stock in data:
                strategy = stock.get("策略", "未知")
                stats["strategies"][strategy] = stats["strategies"].get(strategy, 0) + 1

        return api_success(statistics=stats)
    except Exception as exc:
        return api_error(str(exc))


if __name__ == "__main__":
    os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)

    print("启动Web界面...")
    print("访问地址: http://localhost:5080")
    print("按Ctrl+C停止服务")

    app.run(host="0.0.0.0", port=5080, debug=True)
