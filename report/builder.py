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
        self.drilldown_engine = DrilldownEngine(report_config)

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

    def build_trend_chart(self, metric_result: MetricResult) -> Dict[str, Any]:
        df = metric_result.values.copy()

        if "period" not in df.columns:
            logger.warning("Trend chart requires time series data")
            return {}

        df = df.sort_values("period")

        dim_cols = [c for c in metric_result.dimensions if c in df.columns]

        x_axis = df["period"].astype(str).tolist()

        series = []
        y_values = df["metric_value"].tolist()

        series.append({
            "name": metric_result.label,
            "type": "line",
            "smooth": True,
            "data": [self._format_value(v) for v in y_values],
            "lineStyle": {"width": 3},
            "symbol": "circle",
            "symbolSize": 6
        })

        ma_cols = [c for c in df.columns if c.startswith("ma_")]
        for col in ma_cols:
            window = col.replace("ma_", "")
            series.append({
                "name": f"{window}日移动平均",
                "type": "line",
                "smooth": True,
                "data": [self._format_value(v) for v in df[col].tolist()],
                "lineStyle": {"type": "dashed", "width": 2},
                "symbol": "none"
            })

        return {
            "title": {"text": f"{metric_result.label} - 趋势图", "left": "center"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": [s["name"] for s in series], "bottom": 0},
            "grid": {"left": "3%", "right": "4%", "bottom": "10%", "containLabel": True},
            "xAxis": {"type": "category", "data": x_axis, "axisLabel": {"rotate": 45}},
            "yAxis": {"type": "value"},
            "series": series
        }

    def build_bar_chart(self, metric_result: MetricResult,
                        dimension: str, top_n: int = 10) -> Dict[str, Any]:
        df = metric_result.values.copy()

        if "period" in df.columns:
            latest_period = df["period"].max()
            df = df[df["period"] == latest_period]

        if dimension not in df.columns:
            logger.warning(f"Dimension '{dimension}' not found for bar chart")
            return {}

        dim_df = df.groupby(dimension, dropna=False)["metric_value"].sum().reset_index()
        dim_df = dim_df.sort_values("metric_value", ascending=False).head(top_n)

        categories = [str(v) for v in dim_df[dimension].tolist()]
        values = [self._format_value(v) for v in dim_df["metric_value"].tolist()]

        return {
            "title": {"text": f"{metric_result.label} - {dimension} TOP{top_n}", "left": "center"},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
            "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 45}},
            "yAxis": {"type": "value"},
            "series": [{
                "name": metric_result.label,
                "type": "bar",
                "data": values,
                "itemStyle": {"color": "#5470c6"},
                "label": {"show": True, "position": "top"}
            }]
        }

    def build_waterfall_chart(self, drilldown_result: DrilldownResult) -> Dict[str, Any]:
        if not drilldown_result.waterfall:
            return {}

        labels = [w.label for w in drilldown_result.waterfall]
        values = [self._format_value(w.value) for w in drilldown_result.waterfall]
        types = [w.item_type for w in drilldown_result.waterfall]

        return {
            "title": {"text": "GMV贡献度瀑布分解", "left": "center"},
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "shadow"},
                "formatter": "{b}: ¥{c}"
            },
            "grid": {"left": "3%", "right": "4%", "bottom": "15%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": {"interval": 0, "rotate": 30}
            },
            "yAxis": {"type": "value"},
            "series": [{
                "name": "GMV变化",
                "type": "bar",
                "stack": "total",
                "itemStyle": {
                    "color": "rgba(0,0,0,0)"
                },
                "data": [0 if i < len(values) - 1 else values[-1] for i in range(len(values))]
            }, {
                "name": "增量",
                "type": "bar",
                "stack": "total",
                "data": [
                    0 if t == "base" or t == "total"
                    else abs(v) if v > 0 else 0
                    for v, t in zip(values, types)
                ],
                "itemStyle": {"color": "#91cc75"}
            }, {
                "name": "减量",
                "type": "bar",
                "stack": "total",
                "data": [
                    0 if t == "base" or t == "total"
                    else abs(v) if v < 0 else 0
                    for v, t in zip(values, types)
                ],
                "itemStyle": {"color": "#ee6666"}
            }]
        }

    def build_heatmap(self, metric_result: MetricResult,
                       x_dim: str, y_dim: str) -> Dict[str, Any]:
        df = metric_result.values.copy()

        if "period" in df.columns:
            latest_period = df["period"].max()
            df = df[df["period"] == latest_period]

        if x_dim not in df.columns or y_dim not in df.columns:
            logger.warning("Dimensions not found for heatmap")
            return {}

        pivot = df.pivot_table(
            index=y_dim, columns=x_dim, values="metric_value", aggfunc="sum"
        ).fillna(0)

        x_cats = [str(c) for c in pivot.columns.tolist()]
        y_cats = [str(i) for i in pivot.index.tolist()]

        data = []
        for i, y in enumerate(y_cats):
            for j, x in enumerate(x_cats):
                val = pivot.iloc[i, j]
                data.append([j, i, self._format_value(val)])

        return {
            "title": {"text": f"{x_dim} vs {y_dim} 热力图", "left": "center"},
            "tooltip": {"position": "top"},
            "grid": {"height": "50%", "top": "10%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": x_cats,
                "splitArea": {"show": True},
                "axisLabel": {"rotate": 45}
            },
            "yAxis": {
                "type": "category",
                "data": y_cats,
                "splitArea": {"show": True}
            },
            "visualMap": {
                "min": 0,
                "max": pivot.max().max(),
                "calculable": True,
                "orient": "horizontal",
                "left": "center",
                "bottom": "5%"
            },
            "series": [{
                "name": metric_result.label,
                "type": "heatmap",
                "data": data,
                "label": {"show": True},
                "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0, 0, 0, 0.5)"}}
            }]
        }

    def build_dimension_filters(self, metric_result: MetricResult) -> Dict[str, List[str]]:
        filters = {}
        df = metric_result.values.copy()

        for dim in self.config.dimensions:
            if dim in df.columns:
                unique_vals = sorted([str(v) for v in df[dim].dropna().unique().tolist()])
                filters[dim] = unique_vals

        return filters

    def build_full_report(self, metric_result: MetricResult,
                         drilldown_result: Optional[DrilldownResult] = None) -> Dict[str, Any]:
        drilldown_result = drilldown_result or self.drilldown_engine.analyze(metric_result)

        drilldown_dict = self.drilldown_engine.to_dict(drilldown_result)

        report_data = {
            "title": self.config.title,
            "generated_at": datetime.now().isoformat(),
            "metric": {
                "name": metric_result.metric_name,
                "label": metric_result.label,
                "total_value": drilldown_dict["total_value"],
                "total_mom_pct": drilldown_dict["total_mom_pct"]
            },
            "trend_chart": self.build_trend_chart(metric_result),
            "waterfall_chart": self.build_waterfall_chart(drilldown_result),
            "dimensions": {},
            "filters": self.build_dimension_filters(metric_result),
            "drilldown": drilldown_dict
        }

        for dim in self.config.dimensions:
            if dim in drilldown_dict["contributions"]:
                report_data["dimensions"][dim] = {
                    "bar_chart": self.build_bar_chart(metric_result, dim, self.config.top_n),
                    "contributions": drilldown_dict["contributions"][dim]
                }

        if len(self.config.dimensions) >= 2:
            report_data["heatmap"] = self.build_heatmap(
                metric_result,
                self.config.dimensions[0],
                self.config.dimensions[1]
            )

        return report_data

    def to_json(self, report_data: Dict[str, Any]) -> str:
        return json.dumps(report_data, ensure_ascii=False, indent=2, default=str)
