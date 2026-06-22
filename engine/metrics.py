import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import logging

from config.loader import MetricConfig

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    metric_name: str
    label: str
    values: pd.DataFrame
    time_grain: str
    dimensions: List[str]
    calculation_method: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "label": self.label,
            "time_grain": self.time_grain,
            "dimensions": self.dimensions,
            "calculation_method": self.calculation_method,
            "values": self.values.replace({np.nan: None}).to_dict("records")
        }


class MetricsEngine:
    def __init__(self, df: pd.DataFrame, timestamp_col: str = "order_date"):
        self.df = df.copy()
        self.timestamp_col = timestamp_col
        self._ensure_timestamp()

    def _ensure_timestamp(self) -> None:
        if self.timestamp_col in self.df.columns:
            self.df[self.timestamp_col] = pd.to_datetime(self.df[self.timestamp_col])
        else:
            logger.warning(f"Timestamp column '{self.timestamp_col}' not found in DataFrame")

    def _apply_filters(self, filters: List[Any]) -> pd.DataFrame:
        df = self.df.copy()
        for f in filters:
            if not hasattr(f, "field") or not hasattr(f, "operator") or not hasattr(f, "value"):
                continue

            field, op, value = f.field, f.operator, f.value

            if field not in df.columns:
                logger.warning(f"Filter field '{field}' not found, skipping")
                continue

            try:
                if op == "=":
                    df = df[df[field] == value]
                elif op == "!=":
                    df = df[df[field] != value]
                elif op == ">":
                    df = df[df[field] > value]
                elif op == ">=":
                    df = df[df[field] >= value]
                elif op == "<":
                    df = df[df[field] < value]
                elif op == "<=":
                    df = df[df[field] <= value]
                elif op.lower() == "in":
                    df = df[df[field].isin(value)]
                elif op.lower() == "not in":
                    df = df[~df[field].isin(value)]
                elif op.lower() == "like":
                    df = df[df[field].astype(str).str.contains(str(value).replace("%", ""))]
            except Exception as e:
                logger.warning(f"Filter application failed for {field} {op} {value}: {e}")

        return df

    def _aggregate(self, df: pd.DataFrame, metric_config: MetricConfig,
                   group_cols: List[str]) -> pd.DataFrame:
        expr = metric_config.expression
        method = metric_config.calculation_method.lower()

        if method == "sum":
            agg_df = df.groupby(group_cols, dropna=False)[expr].sum().reset_index()
        elif method == "count":
            agg_df = df.groupby(group_cols, dropna=False)[expr].count().reset_index()
        elif method == "countdistinct":
            agg_df = df.groupby(group_cols, dropna=False)[expr].nunique().reset_index()
        elif method == "avg" or method == "average":
            agg_df = df.groupby(group_cols, dropna=False)[expr].mean().reset_index()
        elif method == "min":
            agg_df = df.groupby(group_cols, dropna=False)[expr].min().reset_index()
        elif method == "max":
            agg_df = df.groupby(group_cols, dropna=False)[expr].max().reset_index()
        elif method == "median":
            agg_df = df.groupby(group_cols, dropna=False)[expr].median().reset_index()
        else:
            logger.warning(f"Unsupported calculation method: {method}, using sum")
            agg_df = df.groupby(group_cols, dropna=False)[expr].sum().reset_index()

        agg_df.rename(columns={expr: "metric_value"}, inplace=True)
        return agg_df

    def _add_time_grain(self, df: pd.DataFrame, time_grain: str) -> pd.DataFrame:
        if self.timestamp_col not in df.columns:
            return df

        df = df.copy()
        if time_grain == "day":
            df["period"] = df[self.timestamp_col].dt.date
        elif time_grain == "week":
            df["period"] = df[self.timestamp_col].dt.to_period("W").dt.to_timestamp()
        elif time_grain == "month":
            df["period"] = df[self.timestamp_col].dt.to_period("M").dt.to_timestamp()
        elif time_grain == "quarter":
            df["period"] = df[self.timestamp_col].dt.to_period("Q").dt.to_timestamp()
        elif time_grain == "year":
            df["period"] = df[self.timestamp_col].dt.to_period("Y").dt.to_timestamp()
        else:
            df["period"] = df[self.timestamp_col].dt.date

        return df

    def calculate_metric(self, metric_config: MetricConfig,
                         time_grain: str = "day",
                         dimensions: Optional[List[str]] = None) -> MetricResult:
        dimensions = dimensions or metric_config.dimensions
        filtered_df = self._apply_filters(metric_config.filters)

        if time_grain and self.timestamp_col in filtered_df.columns:
            filtered_df = self._add_time_grain(filtered_df, time_grain)
            group_cols = ["period"] + [d for d in dimensions if d in filtered_df.columns]
        else:
            group_cols = [d for d in dimensions if d in filtered_df.columns]

        if not group_cols:
            group_cols = [pd.Series(True, index=filtered_df.index, name="all")]

        agg_df = self._aggregate(filtered_df, metric_config, group_cols)

        return MetricResult(
            metric_name=metric_config.name,
            label=metric_config.label,
            values=agg_df,
            time_grain=time_grain,
            dimensions=dimensions,
            calculation_method=metric_config.calculation_method
        )

    def add_yoy(self, result: MetricResult) -> MetricResult:
        df = result.values.copy()
        if "period" not in df.columns:
            logger.warning("YoY calculation requires time series data with 'period' column")
            return result

        df = df.sort_values("period")
        dim_cols = [c for c in result.dimensions if c in df.columns]

        if dim_cols:
            df["metric_value_prev_year"] = df.groupby(dim_cols)["metric_value"].shift(365)
        else:
            df["metric_value_prev_year"] = df["metric_value"].shift(365)

        df["yoy_value"] = df["metric_value"] - df["metric_value_prev_year"]
        df["yoy_pct"] = np.where(
            df["metric_value_prev_year"] != 0,
            (df["metric_value"] / df["metric_value_prev_year"] - 1) * 100,
            np.nan
        )

        result.values = df
        return result

    def add_mom(self, result: MetricResult, periods: int = 1) -> MetricResult:
        df = result.values.copy()
        if "period" not in df.columns:
            logger.warning("MoM calculation requires time series data with 'period' column")
            return result

        df = df.sort_values("period")
        dim_cols = [c for c in result.dimensions if c in df.columns]

        if dim_cols:
            df[f"metric_value_prev_{periods}"] = df.groupby(dim_cols)["metric_value"].shift(periods)
        else:
            df[f"metric_value_prev_{periods}"] = df["metric_value"].shift(periods)

        df[f"mom_{periods}_value"] = df["metric_value"] - df[f"metric_value_prev_{periods}"]
        df[f"mom_{periods}_pct"] = np.where(
            df[f"metric_value_prev_{periods}"] != 0,
            (df["metric_value"] / df[f"metric_value_prev_{periods}"] - 1) * 100,
            np.nan
        )

        result.values = df
        return result

    def add_moving_average(self, result: MetricResult, windows: List[int]) -> MetricResult:
        df = result.values.copy()
        if "period" not in df.columns:
            logger.warning("Moving average requires time series data with 'period' column")
            return result

        df = df.sort_values("period")
        dim_cols = [c for c in result.dimensions if c in df.columns]

        for window in windows:
            col_name = f"ma_{window}"
            if dim_cols:
                df[col_name] = df.groupby(dim_cols)["metric_value"].transform(
                    lambda x: x.rolling(window=window, min_periods=1).mean()
                )
            else:
                df[col_name] = df["metric_value"].rolling(window=window, min_periods=1).mean()

        result.values = df
        return result

    def calculate_full_metric(self, metric_config: MetricConfig,
                              time_grain: str = "day",
                              dimensions: Optional[List[str]] = None,
                              yoy: bool = True,
                              mom: bool = True,
                              mom_periods: int = 1,
                              moving_average_windows: Optional[List[int]] = None) -> MetricResult:
        result = self.calculate_metric(metric_config, time_grain, dimensions)

        if yoy:
            result = self.add_yoy(result)
        if mom:
            result = self.add_mom(result, mom_periods)
        if moving_average_windows:
            result = self.add_moving_average(result, moving_average_windows)

        return result

    def get_period_total(self, result: MetricResult,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> float:
        df = result.values.copy()

        if start_date and "period" in df.columns:
            df = df[df["period"] >= pd.to_datetime(start_date)]
        if end_date and "period" in df.columns:
            df = df[df["period"] <= pd.to_datetime(end_date)]

        return float(df["metric_value"].sum())
