import pandas as pd
import numpy as np
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import logging

from config.loader import ReportConfig
from engine.metrics import MetricResult, MetricsEngine
from engine.drilldown import DrilldownEngine, DrilldownResult

logger = logging.getLogger(__name__)


@dataclass
class EChartOption:
    pass


class ReportBuilder:
    def __init__(self, report_config: ReportConfig):
        self.config = report_config

    def _format_value(self, value: Any, precision: int = 2) -> Any:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        if isinstance(value, float):
            return round(value, precision)
        if isinstance(value, (np.int64, np.int32)):
            return int(value)
        if isinstance(value, (datetime, pd.Timestamp, pd.Period)):
            return str(value)
        return value

    def _df_to_records(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                record[col] = self._format_value(row[col])
            records.append(record)
        return records

    def build_overall_trend_data(self, metric_result: MetricResult,
                                  moving_average_windows: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        df = metric_result.values.copy()

        if "period" not in df.columns:
            return []

        overall = df.groupby("period", dropna=False)["metric_value"].sum().reset_index()
        overall = overall.sort_values("period")

        if moving_average_windows:
            for window in moving_average_windows:
                overall[f"ma_{window}"] = (
                    overall["metric_value"]
                    .rolling(window=window, min_periods=1)
                    .mean()
                )

        return self._df_to_records(overall)

    def build_dimension_mom_data(self, metric_result: MetricResult,
                                  dimension: str) -> Dict[str, Any]:
        df = metric_result.values.copy()

        if "period" not in df.columns or dimension not in df.columns:
            return {"values": [], "anomalies": []}

        periods = sorted(df["period"].dropna().unique().tolist())
        if len(periods) < 2:
            return {"values": [], "anomalies": []}

        latest_period = periods[-1]
        prev_period = periods[-2]

        latest_df = df[df["period"] == latest_period]
        prev_df = df[df["period"] == prev_period]

        latest_agg = latest_df.groupby(dimension, dropna=False)["metric_value"].sum().reset_index()
        prev_agg = prev_df.groupby(dimension, dropna=False)["metric_value"].sum().reset_index()

        latest_agg.columns = [dimension, "latest_value"]
        prev_agg.columns = [dimension, "prev_value"]

        merged = pd.merge(latest_agg, prev_agg, on=dimension, how="outer").fillna(0)
        merged["mom_value"] = merged["latest_value"] - merged["prev_value"]
        merged["mom_pct"] = np.where(
            merged["prev_value"] != 0,
            (merged["latest_value"] / merged["prev_value"] - 1) * 100,
            np.nan
        )
        merged["contribution_pct"] = np.where(
            merged["latest_value"].sum() != 0,
            merged["latest_value"] / merged["latest_value"].sum() * 100,
            0
        )

        merged = merged.sort_values("latest_value", ascending=False).head(self.config.top_n)

        threshold = self.config.anomaly_threshold * 100
        merged["is_anomaly"] = merged["mom_pct"].apply(
            lambda x: bool(pd.notna(x) and abs(x) >= threshold)
        )
        merged["anomaly_direction"] = merged.apply(
            lambda row: "up" if row["is_anomaly"] and row["mom_pct"] > 0
                       else ("down" if row["is_anomaly"] and row["mom_pct"] < 0 else None),
            axis=1
        )

        values = []
        anomalies = []
        for _, row in merged.iterrows():
            item = {
                "dimension": dimension,
                "value": str(row[dimension]) if pd.notna(row[dimension]) else "NULL",
                "metric_value": self._format_value(row["latest_value"]),
                "prev_value": self._format_value(row["prev_value"]),
                "mom_value": self._format_value(row["mom_value"]),
                "mom_pct": self._format_value(row["mom_pct"]) if pd.notna(row["mom_pct"]) else None,
                "contribution_pct": self._format_value(row["contribution_pct"]),
                "is_anomaly": bool(row["is_anomaly"]),
                "anomaly_direction": row["anomaly_direction"]
            }
            values.append(item)
            if item["is_anomaly"]:
                anomalies.append(item)

        return {"values": values, "anomalies": anomalies}

    def build_raw_data(self, metric_result: MetricResult) -> List[Dict[str, Any]]:
        df = metric_result.values.copy()

        if "period" not in df.columns:
            return []

        keep_cols = ["period", "metric_value"] + [
            d for d in self.config.drilldown_dimensions if d in df.columns
        ]

        df = df[keep_cols].copy()
        return self._df_to_records(df)

    def build_waterfall_data(self, metric_result: MetricResult) -> List[Dict[str, Any]]:
        df = metric_result.values.copy()

        if "period" not in df.columns:
            return []

        periods = sorted(df["period"].dropna().unique().tolist())
        if len(periods) < 2:
            return []

        latest_period = periods[-1]
        prev_period = periods[-2]

        latest_total = df[df["period"] == latest_period]["metric_value"].sum()
        prev_total = df[df["period"] == prev_period]["metric_value"].sum()

        waterfall = []
        waterfall.append({"label": "上期总额", "value": self._format_value(prev_total), "type": "base"})

        increase_items = []
        decrease_items = []

        for dim in self.config.dimensions:
            if dim not in df.columns:
                continue

            latest_dim = df[df["period"] == latest_period].groupby(dim)["metric_value"].sum()
            prev_dim = df[df["period"] == prev_period].groupby(dim)["metric_value"].sum()

            diff = (latest_dim - prev_dim).fillna(0)

            if len(diff) == 0:
                continue

            top_inc_idx = diff.idxmax()
            top_dec_idx = diff.idxmin()

            if diff.loc[top_inc_idx] > 0:
                increase_items.append({
                    "label": f"{dim}: {top_inc_idx} 拉升",
                    "value": self._format_value(diff.loc[top_inc_idx])
                })

            if diff.loc[top_dec_idx] < 0:
                decrease_items.append({
                    "label": f"{dim}: {top_dec_idx} 拖累",
                    "value": self._format_value(diff.loc[top_dec_idx])
                })

        for item in increase_items[:3]:
            waterfall.append({**item, "type": "increase"})
        for item in decrease_items[:3]:
            waterfall.append({**item, "type": "decrease"})

        waterfall.append({"label": "本期总额", "value": self._format_value(latest_total), "type": "total"})

        return waterfall

    def build_overall_kpi(self, metric_result: MetricResult) -> Dict[str, Any]:
        df = metric_result.values.copy()

        if "period" not in df.columns:
            return {"total_value": self._format_value(df["metric_value"].sum()), "total_mom_pct": None}

        periods = sorted(df["period"].dropna().unique().tolist())
        if len(periods) == 0:
            return {"total_value": 0, "total_mom_pct": None}

        latest_period = periods[-1]
        latest_total = df[df["period"] == latest_period]["metric_value"].sum()

        if len(periods) >= 2:
            prev_period = periods[-2]
            prev_total = df[df["period"] == prev_period]["metric_value"].sum()
            mom_pct = ((latest_total - prev_total) / prev_total * 100) if prev_total != 0 else None
        else:
            mom_pct = None

        return {
            "total_value": self._format_value(latest_total),
            "total_mom_pct": self._format_value(mom_pct) if mom_pct is not None else None
        }

    def build_full_report(self, metric_result: MetricResult,
                         drilldown_result: Optional[DrilldownResult] = None) -> Dict[str, Any]:
        kpi = self.build_overall_kpi(metric_result)

        dimensions_data = {}
        all_anomalies = []

        for dim in self.config.dimensions:
            dim_mom = self.build_dimension_mom_data(metric_result, dim)
            dimensions_data[dim] = dim_mom["values"]
            all_anomalies.extend(dim_mom["anomalies"])

        all_anomalies.sort(key=lambda x: abs(x.get("mom_pct") or 0), reverse=True)

        overall_trend = self.build_overall_trend_data(
            metric_result, self.config.moving_average_windows
        )

        raw_data = self.build_raw_data(metric_result)
        waterfall = self.build_waterfall_data(metric_result)

        filters = {}
        df = metric_result.values.copy()
        for dim in self.config.dimensions:
            if dim in df.columns:
                unique_vals = sorted([str(v) for v in df[dim].dropna().unique().tolist()])
                filters[dim] = unique_vals

        drilldown_map = {
            "category": ["subcategory"],
            "region": ["category", "channel"],
            "channel": ["category", "region"]
        }

        report_data = {
            "title": self.config.title,
            "generated_at": datetime.now().isoformat(),
            "metric": {
                "name": metric_result.metric_name,
                "label": metric_result.label,
                **kpi
            },
            "config": {
                "dimensions": self.config.dimensions,
                "drilldown_dimensions": self.config.drilldown_dimensions,
                "drilldown_map": drilldown_map,
                "anomaly_threshold": self.config.anomaly_threshold,
                "top_n": self.config.top_n,
                "time_grain": metric_result.time_grain
            },
            "overall_trend": overall_trend,
            "waterfall": waterfall,
            "dimensions": dimensions_data,
            "anomalies": all_anomalies,
            "raw_data": raw_data,
            "filters": filters,
            "ma_windows": self.config.moving_average_windows
        }

        return report_data

    def to_json(self, report_data: Dict[str, Any]) -> str:
        return json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
