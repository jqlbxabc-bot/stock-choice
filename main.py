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
        "adaptive_multifactor": "自适应多因子主策略",
    }

    DEFAULT_WEIGHTS = {
        "high_freq": {"amplitude": 0.4, "turnover": 0.3, "price_change": 0.2, "price_level": 0.1},
        "momentum_breakout": {"price_change": 0.4, "amplitude": 0.3, "turnover": 0.3},
        "noon_rush": {"turnover": 0.5, "price_change": 0.3, "amplitude": 0.2},
        "tail_strength": {"price_change": 0.5, "turnover": 0.3, "amplitude": 0.2},
        "10x_stock": {"price_level": 0.3, "turnover": 0.4, "price_change": 0.3},
        "sector_leaders": {"turnover": 0.4, "price_change": 0.4, "amplitude": 0.2},
        "adaptive_multifactor": {"trend": 0.24, "momentum": 0.22, "volume": 0.14, "liquidity": 0.10, "volatility": 0.10, "position": 0.08, "size": 0.07, "intraday": 0.05},
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
            "adaptive_multifactor": self._adaptive_multifactor_selection,
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
                {"id": "sector_leaders", "name": "板块龙头策略", "enabled": False},
                {"id": "adaptive_multifactor", "name": "自适应多因子主策略", "enabled": True},
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
        """获取并标准化A股实时快照；优先东方财富接口，失败时自动回退。"""
        print("正在获取股票实时数据...")
        errors = []
        getters = [
            ("eastmoney", getattr(ak, "stock_zh_a_spot_em", None)),
            ("legacy", getattr(ak, "stock_zh_a_spot", None)),
        ]
        for source_name, getter in getters:
            if getter is None:
                continue
            try:
                df = getter()
                df = self._normalize_stock_data(df)
                self.stock_data = df
                print(f"实时数据源={source_name}，获取到 {len(df)} 只股票")
                return df
            except Exception as exc:
                errors.append(f"{source_name}: {exc}")
        print("获取实时数据失败: " + " | ".join(errors))
        return None

    def _normalize_stock_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """统一 akshare 返回列名与数值类型。"""
        if df.empty:
            raise ValueError("数据源返回空数据")

        # 优先使用显式列名；仅在完全无法识别时才回退到旧接口的位置映射。
        aliases = {
            "代码": ["代码", "股票代码"],
            "名称": ["名称", "股票名称"],
            "最新价": ["最新价", "现价"],
            "涨跌幅": ["涨跌幅"],
            "昨收": ["昨收"],
            "今开": ["今开"],
            "最高": ["最高"],
            "最低": ["最低"],
            "成交额": ["成交额"],
        }
        rename_map = {}
        for target, candidates in aliases.items():
            if target in df.columns:
                continue
            for src in candidates:
                if src in df.columns:
                    rename_map[src] = target
                    break
        if rename_map:
            df = df.rename(columns=rename_map)

        if "代码" not in df.columns:
            positional = {
                df.columns[index]: column_name
                for index, column_name in self.COLUMN_MAPPING.items()
                if index < len(df.columns)
            }
            df = df.rename(columns=positional)

        missing_columns = [column for column in self.REQUIRED_COLUMNS if column not in df.columns]
        if missing_columns:
            raise ValueError(f"股票数据缺少必要字段: {', '.join(missing_columns)}")

        # 尽量保留行情源中的附加字段，供多因子主策略使用。
        optional_aliases = {
            "换手率": ["换手率"], "量比": ["量比"], "总市值": ["总市值"],
            "流通市值": ["流通市值"], "市盈率-动态": ["市盈率-动态", "动态市盈率"],
            "市净率": ["市净率"],
        }
        for target, candidates in optional_aliases.items():
            if target not in df.columns:
                for src in candidates:
                    if src in df.columns:
                        df[target] = df[src]
                        break

        numeric_columns = ["最新价", "涨跌幅", "成交额", "昨收", "最高", "最低"]
        numeric_columns += [c for c in optional_aliases if c in df.columns]
        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna(subset=numeric_columns).copy()
        df["振幅"] = np.where(df["昨收"] > 0, (df["最高"] - df["最低"]) / df["昨收"] * 100, 0)
        df["is_chinext"] = df["代码"].astype(str).str.startswith(("sz300", "sz301", "300", "301"))
        df.attrs["snapshot_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def _market_regime(self) -> str:
        """用全市场横截面判断风险环境：risk_on / neutral / risk_off。"""
        if self.stock_data is None or self.stock_data.empty:
            return "neutral"
        df = self.stock_data
        adv = (df["涨跌幅"] > 0).mean()
        strong = (df["涨跌幅"] >= 2).mean()
        weak = (df["涨跌幅"] <= -2).mean()
        if adv >= 0.58 and strong >= weak * 1.15:
            return "risk_on"
        if adv <= 0.42 and weak >= strong * 1.15:
            return "risk_off"
        return "neutral"

    @staticmethod
    def _hist_symbol(code: str) -> str:
        code = str(code).lower().replace("sh", "").replace("sz", "")
        return code.zfill(6)

    def _fetch_hist_features(self, code: str, lookback_days: int = 90) -> dict:
        """取日线历史特征。失败时返回空字典，不用旧数据冒充。"""
        try:
            end = datetime.datetime.now().strftime("%Y%m%d")
            start = (datetime.datetime.now() - datetime.timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
            h = ak.stock_zh_a_hist(
                symbol=self._hist_symbol(code),
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            if h is None or len(h) < 25:
                return {}
            h = h.tail(lookback_days).copy()
            for c in ["收盘", "最高", "最低", "成交量", "成交额"]:
                if c in h.columns:
                    h[c] = pd.to_numeric(h[c], errors="coerce")
            h = h.dropna(subset=["收盘"])
            if len(h) < 25:
                return {}

            close = h["收盘"]
            ret5 = (close.iloc[-1] / close.iloc[-6] - 1) * 100 if len(close) >= 6 else np.nan
            ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 21 else np.nan
            ret60 = (close.iloc[-1] / close.iloc[-61] - 1) * 100 if len(close) >= 61 else np.nan

            ma5 = close.tail(5).mean()
            ma20 = close.tail(20).mean()
            ma60 = close.tail(60).mean() if len(close) >= 60 else np.nan
            trend_stack = float(ma5 > ma20) + (float(ma20 > ma60) if not pd.isna(ma60) else 0.0)

            high20 = h["最高"].tail(20).max() if "最高" in h.columns else close.tail(20).max()
            position20 = close.iloc[-1] / high20 if high20 else 0

            if {"最高", "最低"}.issubset(h.columns):
                prev = close.shift(1)
                tr = pd.concat([
                    h["最高"] - h["最低"],
                    (h["最高"] - prev).abs(),
                    (h["最低"] - prev).abs(),
                ], axis=1).max(axis=1)
                atr14 = tr.tail(14).mean()
                atr_pct = atr14 / close.iloc[-1] * 100 if close.iloc[-1] else np.nan
            else:
                atr_pct = np.nan

            vol_ratio20 = np.nan
            if "成交量" in h.columns and len(h) >= 21:
                base = h["成交量"].iloc[-21:-1].mean()
                if base and not pd.isna(base):
                    vol_ratio20 = h["成交量"].iloc[-1] / base

            return {
                "ret5": ret5, "ret20": ret20, "ret60": ret60,
                "trend_stack": trend_stack, "position20": position20,
                "atr_pct": atr_pct, "vol_ratio20": vol_ratio20,
            }
        except Exception:
            return {}

    def _adaptive_multifactor_selection(self, params: dict, exclude_list: list[str] | None = None, round_num: int = 1) -> list[dict]:
        """
        主策略：两级漏斗。
        1) 横截面快速预筛：流动性/价格/涨幅/市值/非ST。
        2) 对较小候选池补历史趋势、5/20/60日动量、量能、ATR，再按市场状态动态加权。
        """
        print("执行自适应多因子主策略...")
        df = self.stock_data.copy()

        # 基础可交易性过滤
        name = df["名称"].astype(str)
        mask = (
            ~name.str.contains("ST|退", case=False, regex=True)
            & (df["最新价"] >= params.get("price_min", 4))
            & (df["最新价"] <= params.get("price_max", 180))
            & (df["成交额"] >= params.get("turnover_min", 200000000))
            & (df["涨跌幅"] >= params.get("change_min", -3.5))
            & (df["涨跌幅"] <= params.get("change_max", 7.5))
        )
        if "总市值" in df.columns:
            cap_min = params.get("market_cap_min", 10000000000)
            cap_max = params.get("market_cap_max", 50000000000)
            cap = pd.to_numeric(df["总市值"], errors="coerce")
            mask &= cap.between(cap_min, cap_max)

        pool = df[mask].copy()
        if exclude_list:
            pool = pool[~pool["代码"].isin(exclude_list)]
        if pool.empty:
            return []

        # 一级快筛：成交额 + 温和动量 + 换手/量比（如果数据源提供）
        pool["pre_score"] = (
            self._normalize_score(np.log1p(pool["成交额"])) * 0.45
            + (100 - (pool["涨跌幅"] - params.get("ideal_change", 2.5)).abs() * 12).clip(0,100) * 0.30
            + self._normalize_score(pool["振幅"].clip(0, 12)) * 0.10
        )
        if "量比" in pool.columns:
            vr = pd.to_numeric(pool["量比"], errors="coerce").fillna(1.0).clip(0, 4)
            pool["pre_score"] += self._normalize_score(vr) * 0.10
        if "换手率" in pool.columns:
            tor = pd.to_numeric(pool["换手率"], errors="coerce").fillna(0).clip(0, 20)
            # 不是越高越好，5%-12%左右更适合短线流动性与不过热的平衡
            pool["pre_score"] += (100 - (tor - 8).abs() * 9).clip(0,100) * 0.05

        pre_count = int(params.get("prefilter_count", 80))
        pool = pool.nlargest(min(pre_count, len(pool)), "pre_score").copy()

        # 二级补历史特征
        feats = []
        for code in pool["代码"]:
            f = self._fetch_hist_features(code, int(params.get("history_lookback", 90)))
            feats.append(f)
        feat_df = pd.DataFrame(feats, index=pool.index)
        for col in ["ret5","ret20","ret60","trend_stack","position20","atr_pct","vol_ratio20"]:
            pool[col] = feat_df[col] if col in feat_df else np.nan

        coverage = pool["ret20"].notna().mean()
        if coverage < params.get("min_history_coverage", 0.55):
            print(f"历史特征覆盖率仅 {coverage:.0%}，主策略停止输出，避免用残缺数据硬选。")
            return []

        regime = self._market_regime()
        weights = dict(self._score_weights("adaptive_multifactor"))
        if regime == "risk_on":
            weights["momentum"] += 0.05
            weights["volatility"] -= 0.03
            weights["position"] -= 0.02
        elif regime == "risk_off":
            weights["momentum"] -= 0.05
            weights["volatility"] += 0.05
            weights["position"] += 0.02

        # 因子分数
        trend = (pool["trend_stack"].fillna(0) / 2 * 100).clip(0,100)
        # 5日防止追高，20日为主，60日确认中期方向
        mom5 = (100 - (pool["ret5"].fillna(0) - 4).abs() * 10).clip(0,100)
        mom20 = (pool["ret20"].fillna(-20) * 3 + 50).clip(0,100)
        mom60 = (pool["ret60"].fillna(0) * 1.5 + 50).clip(0,100)
        momentum = mom5 * 0.25 + mom20 * 0.50 + mom60 * 0.25

        volr = pool["vol_ratio20"].fillna(1.0).clip(0,4)
        volume = (100 - (volr - 1.5).abs() * 45).clip(0,100)
        liquidity = self._normalize_score(np.log1p(pool["成交额"]))

        atr = pool["atr_pct"].fillna(pool["atr_pct"].median()).fillna(4.0)
        # 短线偏好有波动但不极端：约2.5%-5.5%
        volatility = (100 - (atr - 4.0).abs() * 20).clip(0,100)

        pos = pool["position20"].fillna(0.8)
        # 接近20日高点但不要求贴着涨停：0.90~0.99更优
        position = (100 - (pos - 0.95).abs() * 500).clip(0,100)

        intraday = (100 - (pool["涨跌幅"] - params.get("ideal_change", 2.5)).abs() * 14).clip(0,100)

        if "总市值" in pool.columns:
            cap = pd.to_numeric(pool["总市值"], errors="coerce")
            ideal_cap = params.get("ideal_market_cap", 25000000000)
            size = (100 - ((cap - ideal_cap).abs() / max(ideal_cap,1) * 70)).clip(0,100).fillna(50)
        else:
            size = pd.Series(50,index=pool.index)

        pool["评分"] = (
            trend * weights["trend"]
            + momentum * weights["momentum"]
            + volume * weights["volume"]
            + liquidity * weights["liquidity"]
            + volatility * weights["volatility"]
            + position * weights["position"]
            + size * weights["size"]
            + intraday * weights["intraday"]
        )

        # 硬性风险扣分：追高、过度波动、趋势破坏
        pool.loc[pool["涨跌幅"] > params.get("chase_penalty_from", 5.5), "评分"] -= 12
        pool.loc[pool["atr_pct"] > params.get("atr_max", 7.5), "评分"] -= 10
        pool.loc[pool["ret20"] < params.get("ret20_min", -3), "评分"] -= 15
        pool.loc[pool["trend_stack"] < 1, "评分"] -= 12

        selected = pool.nlargest(int(params.get("selection_count", 5)), "评分")
        result = self._build_result(selected, "自适应多因子主策略", round_num, score_column="评分")
        for item, (_, row) in zip(result, selected.iterrows()):
            item["市场状态"] = regime
            item["5日强度"] = None if pd.isna(row["ret5"]) else round(float(row["ret5"]),2)
            item["20日强度"] = None if pd.isna(row["ret20"]) else round(float(row["ret20"]),2)
            item["60日强度"] = None if pd.isna(row["ret60"]) else round(float(row["ret60"]),2)
            item["ATR%"] = None if pd.isna(row["atr_pct"]) else round(float(row["atr_pct"]),2)
            item["量能比"] = None if pd.isna(row["vol_ratio20"]) else round(float(row["vol_ratio20"]),2)
            item["20日位置"] = None if pd.isna(row["position20"]) else round(float(row["position20"]),3)
        print(f"主策略输出 {len(result)} 只；市场状态={regime}；历史覆盖={coverage:.0%}")
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
