#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态选股系统 - 主程序

保留 DynamicStockSelector 对外接口，同时把公共筛选、评分、结果组装逻辑集中起来，
便于后续添加策略或调整配置。
"""

from __future__ import annotations

import datetime
import json
import os
import warnings
from typing import Callable

import akshare as ak
import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")
CONFIG_FILE = os.path.join(BASE_DIR, "config.yaml")

for dir_path in [DATA_DIR, OUTPUT_DIR, LOG_DIR]:
    os.makedirs(dir_path, exist_ok=True)


class DynamicStockSelector:
    """动态选股系统类（支持多策略）。"""

    COLUMN_MAPPING = {
        0: "代码",
        1: "名称",
        2: "最新价",
        4: "涨跌幅",
        7: "昨收",
        8: "今开",
        9: "最高",
        10: "最低",
        12: "成交额",
    }

    REQUIRED_COLUMNS = ["代码", "名称", "最新价", "涨跌幅", "昨收", "最高", "最低", "成交额"]

    STRATEGY_NAMES = {
        "high_freq": "低吸潜伏",
        "momentum_breakout": "动量突破",
        "noon_rush": "午间抢筹",
        "tail_strength": "尾盘强势",
        "10x_stock": "10倍股潜力",
        "sector_leaders": "板块龙头",
    }

    DEFAULT_WEIGHTS = {
        "high_freq": {"amplitude": 0.4, "turnover": 0.3, "price_change": 0.2, "price_level": 0.1},
        "momentum_breakout": {"price_change": 0.4, "amplitude": 0.3, "turnover": 0.3},
        "noon_rush": {"turnover": 0.5, "price_change": 0.3, "amplitude": 0.2},
        "tail_strength": {"price_change": 0.5, "turnover": 0.3, "amplitude": 0.2},
        "10x_stock": {"price_level": 0.3, "turnover": 0.4, "price_change": 0.3},
        "sector_leaders": {"turnover": 0.4, "price_change": 0.4, "amplitude": 0.2},
    }

    def __init__(self, config_file: str | None = None):
        self.stock_data: pd.DataFrame | None = None
        self.selected_stocks: list[dict] = []
        self.excluded_stocks: set[str] = set()
        self.selection_history: list[dict] = []
        self.config = self._load_config(config_file)
        self.strategy_handlers: dict[str, Callable[[dict, list[str] | None, int], list[dict]]] = {
            "high_freq": lambda params, exclude, round_num: self._run_basic_strategy(
                "high_freq", params, self._calculate_high_freq_score, exclude, round_num
            ),
            "momentum_breakout": lambda params, exclude, round_num: self._run_basic_strategy(
                "momentum_breakout", params, self._calculate_momentum_score, exclude, round_num
            ),
            "noon_rush": lambda params, exclude, round_num: self._run_basic_strategy(
                "noon_rush", params, self._calculate_volume_score, exclude, round_num
            ),
            "tail_strength": lambda params, exclude, round_num: self._run_basic_strategy(
                "tail_strength", params, self._calculate_tail_score, exclude, round_num
            ),
            "10x_stock": self._10x_stock_selection,
            "sector_leaders": lambda params, exclude, round_num: self._run_basic_strategy(
                "sector_leaders", params, self._calculate_leader_score, exclude, round_num, chinext_only=False
            ),
        }

    def _load_config(self, config_file: str | None = None) -> dict:
        """加载配置文件。"""
        config_file = config_file or CONFIG_FILE
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            print(f"配置文件加载成功: {config_file}")
            return config
        except Exception as exc:
            print(f"配置文件加载失败: {exc}")
            return self._get_default_config()

    def _get_default_config(self) -> dict:
        """获取默认配置。"""
        return {
            "strategies": [
                {"id": "high_freq", "name": "低吸潜伏策略", "enabled": True},
                {"id": "momentum_breakout", "name": "动量突破策略", "enabled": True},
                {"id": "noon_rush", "name": "午间抢筹策略", "enabled": True},
                {"id": "tail_strength", "name": "尾盘强势策略", "enabled": True},
                {"id": "10x_stock", "name": "10倍股潜力策略", "enabled": True},
                {"id": "sector_leaders", "name": "板块龙头策略", "enabled": True},
            ],
            "high_freq": {
                "price_min": 5,
                "price_max": 100,
                "amplitude_min": 3.0,
                "turnover_min": 150000000,
                "change_min": -5.0,
                "change_max": 1.0,
                "board": "创业板",
                "selection_count": 10,
            },
            "momentum_breakout": {
                "price_min": 5,
                "price_max": 100,
                "amplitude_min": 4.0,
                "turnover_min": 200000000,
                "change_min": 2.0,
                "change_max": 8.0,
                "board": "创业板",
                "selection_count": 10,
            },
            "noon_rush": {
                "price_min": 5,
                "price_max": 100,
                "amplitude_min": 2.5,
                "turnover_min": 150000000,
                "change_min": 0.5,
                "change_max": 5.0,
                "board": "创业板",
                "time_range": "11:00-13:00",
                "selection_count": 10,
            },
            "tail_strength": {
                "price_min": 5,
                "price_max": 100,
                "amplitude_min": 3.0,
                "turnover_min": 150000000,
                "change_min": 1.0,
                "change_max": 6.0,
                "board": "创业板",
                "time_range": "14:00-15:00",
                "selection_count": 10,
            },
            "10x_stock": {"turnover_min": 100000000, "selection_count": 10},
            "sector_leaders": {
                "price_min": 10,
                "price_max": 200,
                "amplitude_min": 2.0,
                "turnover_min": 500000000,
                "change_min": 0.5,
                "change_max": 10.0,
                "board": "全A股",
                "selection_count": 15,
            },
        }

    def get_available_strategies(self) -> list[dict]:
        """获取可用策略列表。"""
        return [
            {
                "id": strategy["id"],
                "name": strategy["name"],
                "description": strategy.get("description", ""),
            }
            for strategy in self.config.get("strategies", [])
            if strategy.get("enabled", True)
        ]

    def get_stock_data(self) -> pd.DataFrame | None:
        """获取并标准化股票数据。"""
        print("正在获取股票数据...")
        try:
            df = ak.stock_zh_a_spot()
            df = self._normalize_stock_data(df)
            self.stock_data = df
            print(f"获取到 {len(df)} 只股票数据")
            return df
        except Exception as exc:
            print(f"获取数据失败: {exc}")
            return None

    def _normalize_stock_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一 akshare 返回列名与数值类型。"""
        if df.empty:
            raise ValueError("数据源返回空数据")

        if df.columns[0] != "代码":
            rename_map = {
                df.columns[index]: column_name
                for index, column_name in self.COLUMN_MAPPING.items()
                if index < len(df.columns)
            }
            df = df.rename(columns=rename_map)

        missing_columns = [column for column in self.REQUIRED_COLUMNS if column not in df.columns]
        if missing_columns:
            raise ValueError(f"股票数据缺少必要字段: {', '.join(missing_columns)}")

        numeric_columns = ["最新价", "涨跌幅", "成交额", "昨收", "最高", "最低"]
        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna(subset=numeric_columns).copy()
        df["振幅"] = np.where(df["昨收"] > 0, (df["最高"] - df["最低"]) / df["昨收"] * 100, 0)
        df["is_chinext"] = df["代码"].astype(str).str.startswith(("sz300", "sz301", "300", "301"))
        return df

    def run_strategy(self, strategy_id: str, exclude_list: list[str] | None = None, round_num: int = 1) -> list[dict]:
        """运行指定策略。"""
        if self.stock_data is None:
            self.get_stock_data()

        if self.stock_data is None:
            return []

        print(f"\n执行策略: {strategy_id} (第{round_num}轮)")
        strategy_params = self.config.get(strategy_id, {})
        if not strategy_params:
            print(f"未找到策略配置: {strategy_id}")
            return []

        handler = self.strategy_handlers.get(strategy_id)
        if handler is None:
            print(f"未知策略: {strategy_id}")
            return []

        return handler(strategy_params, exclude_list, round_num)

    def _run_basic_strategy(
        self,
        strategy_id: str,
        params: dict,
        score_func: Callable[[pd.DataFrame], pd.Series],
        exclude_list: list[str] | None = None,
        round_num: int = 1,
        chinext_only: bool = True,
    ) -> list[dict]:
        """执行价格、涨跌幅、振幅、成交额这一类通用筛选策略。"""
        strategy_name = self.STRATEGY_NAMES.get(strategy_id, strategy_id)
        print(f"执行{strategy_name}策略...")

        if not self._is_strategy_time_allowed(params):
            return []

        filtered_df = self._filter_stocks(params, exclude_list, chinext_only=chinext_only)
        if filtered_df.empty:
            print("没有找到符合条件的股票")
            return []

        filtered_df["评分"] = score_func(filtered_df)
        selection_count = params.get("selection_count", 10)
        selected = filtered_df.nlargest(selection_count, "评分")
        result = self._build_result(selected, strategy_name, round_num, score_column="评分")

        print(f"本轮选出 {len(result)} 只股票")
        return result

    def _filter_stocks(
        self,
        params: dict,
        exclude_list: list[str] | None = None,
        chinext_only: bool = True,
    ) -> pd.DataFrame:
        """按配置过滤股票池。"""
        df = self.stock_data.copy()
        mask = (
            (df["最新价"] >= params["price_min"])
            & (df["最新价"] <= params["price_max"])
            & (df["涨跌幅"] >= params["change_min"])
            & (df["涨跌幅"] <= params["change_max"])
            & (df["振幅"] >= params["amplitude_min"])
            & (df["成交额"] >= params["turnover_min"])
        )

        if chinext_only:
            mask &= df["is_chinext"]

        filtered_df = df[mask].copy()
        if exclude_list:
            filtered_df = filtered_df[~filtered_df["代码"].isin(exclude_list)]
        return filtered_df

    def _is_strategy_time_allowed(self, params: dict) -> bool:
        """检查策略的可运行时间窗口。"""
        time_range = params.get("time_range")
        if not time_range:
            return True

        current_time = datetime.datetime.now().time()
        start_time_str, end_time_str = time_range.split("-")
        start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()

        if start_time <= current_time <= end_time:
            return True

        print(f"当前时间不在策略时间范围内: {time_range}")
        return False

    def _10x_stock_selection(self, params: dict, exclude_list: list[str] | None = None, round_num: int = 1) -> list[dict]:
        """10倍股潜力筛选。"""
        print("执行10倍股潜力策略...")
        df = self.stock_data.copy()
        selected = df[
            df["is_chinext"]
            & (df["成交额"] >= params.get("turnover_min", 100000000))
            & (df["最新价"] >= params.get("price_min", 10))
        ].copy()

        if exclude_list:
            selected = selected[~selected["代码"].isin(exclude_list)]

        if selected.empty:
            print("没有找到符合条件的股票")
            return []

        selected["潜力评分"] = self._calculate_10x_score(selected)
        selection_count = params.get("selection_count", 10)
        result_df = selected.nlargest(selection_count, "潜力评分")
        result = self._build_result(result_df, "10倍股潜力", round_num, score_column="潜力评分", include_amplitude=False)

        print(f"本轮选出 {len(result)} 只潜力股")
        return result

    def _build_result(
        self,
        df: pd.DataFrame,
        strategy_name: str,
        round_num: int,
        score_column: str,
        include_amplitude: bool = True,
    ) -> list[dict]:
        """把 DataFrame 行转换为统一输出结构。"""
        selected_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = []
        for _, row in df.iterrows():
            stock_info = {
                "代码": row["代码"],
                "名称": row["名称"],
                "最新价": row["最新价"],
                "涨跌幅": row["涨跌幅"],
                "成交额": row["成交额"],
                score_column: row[score_column],
                "选择时间": selected_at,
                "策略": strategy_name,
                "轮次": round_num,
            }
            if include_amplitude:
                stock_info["振幅"] = row["振幅"]
            result.append(stock_info)
        return result

    def _score_weights(self, strategy_id: str) -> dict:
        """读取评分权重，缺失项使用默认值。"""
        weights = dict(self.DEFAULT_WEIGHTS.get(strategy_id, {}))
        weights.update(self.config.get("scoring_weights", {}).get(strategy_id, {}))
        return weights

    @staticmethod
    def _normalize_score(series: pd.Series) -> pd.Series:
        """归一化到 0-100，避免单一取值时除零。"""
        value_range = series.max() - series.min()
        if pd.isna(value_range) or value_range == 0:
            return pd.Series(50, index=series.index, dtype="float64")
        return (series - series.min()) / value_range * 100

    def _calculate_high_freq_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("high_freq")
        return (
            self._normalize_score(df["振幅"]) * weights["amplitude"]
            + self._normalize_score(df["成交额"]) * weights["turnover"]
            + (100 - abs(df["涨跌幅"]) * 10).clip(0, 100) * weights["price_change"]
            + (100 - abs(df["最新价"] - 50) * 2).clip(0, 100) * weights["price_level"]
        )

    def _calculate_momentum_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("momentum_breakout")
        return (
            (df["涨跌幅"] * 10).clip(0, 100) * weights["price_change"]
            + self._normalize_score(df["振幅"]) * weights["amplitude"]
            + self._normalize_score(df["成交额"]) * weights["turnover"]
        )

    def _calculate_volume_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("noon_rush")
        return (
            self._normalize_score(df["成交额"]) * weights["turnover"]
            + (100 - abs(df["涨跌幅"]) * 10).clip(0, 100) * weights["price_change"]
            + self._normalize_score(df["振幅"]) * weights["amplitude"]
        )

    def _calculate_tail_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("tail_strength")
        return (
            (df["涨跌幅"] * 15).clip(0, 100) * weights["price_change"]
            + self._normalize_score(df["成交额"]) * weights["turnover"]
            + self._normalize_score(df["振幅"]) * weights["amplitude"]
        )

    def _calculate_10x_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("10x_stock")
        return (
            (100 - abs(df["最新价"] - 30) * 3).clip(0, 100) * weights["price_level"]
            + self._normalize_score(df["成交额"]) * weights["turnover"]
            + (100 - abs(df["涨跌幅"]) * 5).clip(0, 100) * weights["price_change"]
        )

    def _calculate_leader_score(self, df: pd.DataFrame) -> pd.Series:
        weights = self._score_weights("sector_leaders")
        return (
            self._normalize_score(df["成交额"]) * weights["turnover"]
            + (df["涨跌幅"] * 10).clip(0, 100) * weights["price_change"]
            + self._normalize_score(df["振幅"]) * weights["amplitude"]
        )

    def save_selection(self, selection: list[dict], strategy_name: str) -> str:
        """保存选股结果。"""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(OUTPUT_DIR, f"{strategy_name}_{timestamp}.json")

        serializable_data = []
        for item in selection:
            serializable_item = {}
            for key, value in item.items():
                if isinstance(value, (np.integer, np.floating)):
                    serializable_item[key] = value.item()
                else:
                    serializable_item[key] = value
            serializable_data.append(serializable_item)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {json_path}")

        csv_path = os.path.join(OUTPUT_DIR, f"{strategy_name}_{timestamp}.csv")
        pd.DataFrame(serializable_data).to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"CSV结果已保存到: {csv_path}")
        return json_path


def is_market_open(now: datetime.datetime | None = None, config: dict | None = None) -> bool:
    """检查当前是否处于配置的交易时间。"""
    now = now or datetime.datetime.now()
    trading_hours = (config or {}).get("system", {}).get("trading_hours", {})
    start = trading_hours.get("start", "09:30")
    end = trading_hours.get("end", "15:00")
    market_open = datetime.datetime.strptime(start, "%H:%M").time()
    market_close = datetime.datetime.strptime(end, "%H:%M").time()
    return market_open <= now.time() <= market_close


def run_all_strategies(selector: DynamicStockSelector, strategies: list[dict]) -> dict[str, list[dict]]:
    """执行所有当前可运行策略并保存结果。"""
    all_results = {}
    current_time = datetime.datetime.now().time()

    for strategy in strategies:
        strategy_id = strategy["id"]
        params = selector.config.get(strategy_id, {})
        time_range = params.get("time_range")
        if time_range:
            start_time_str, end_time_str = time_range.split("-")
            start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()
            if not (start_time <= current_time <= end_time):
                print(f"\n跳过策略 {strategy['name']} (不在时间范围内: {time_range})")
                continue

        result = selector.run_strategy(strategy_id, round_num=1)
        all_results[strategy_id] = result
        if result:
            selector.save_selection(result, strategy["name"])

    return all_results


def print_summary(all_results: dict[str, list[dict]], strategies: list[dict]) -> None:
    """输出选股结果摘要。"""
    print("\n" + "=" * 40)
    print("选股结果汇总")
    print("=" * 40)

    for strategy_id, result in all_results.items():
        strategy_name = next((s["name"] for s in strategies if s["id"] == strategy_id), strategy_id)
        print(f"\n{strategy_name}: {len(result)} 只股票")
        for index, stock in enumerate(result[:3], 1):
            score = stock.get("评分", stock.get("潜力评分", 0))
            print(
                f"  {index}. {stock['代码']} {stock['名称']} "
                f"价格:{stock['最新价']:.2f} "
                f"涨跌:{stock['涨跌幅']:.2f}% "
                f"评分:{score:.1f}"
            )
        if len(result) > 3:
            print(f"  ... 还有 {len(result) - 3} 只")


def main() -> None:
    """命令行入口。"""
    print("=" * 60)
    print("动态选股系统 - 多策略版本")
    print("=" * 60)

    selector = DynamicStockSelector()
    strategies = selector.get_available_strategies()

    print("\n可用策略:")
    for index, strategy in enumerate(strategies, 1):
        print(f"{index}. {strategy['name']} - {strategy['description']}")

    now = datetime.datetime.now()
    print(f"\n当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    if is_market_open(now, selector.config):
        print("当前在交易时间内")
        print("\n" + "=" * 40)
        print("执行所有策略选股")
        print("=" * 40)
    else:
        print("当前不在交易时间内（9:30-15:00）")
        print("执行选股分析（使用缓存数据，结果可能不是最新行情）...")

    all_results = run_all_strategies(selector, strategies)
    print_summary(all_results, strategies)

    print("\n" + "=" * 60)
    print("选股完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
