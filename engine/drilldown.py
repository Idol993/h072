import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import logging

from config.loader import ReportConfig
from engine.metrics import MetricResult

logger = logging.getLogger(__name__)


@dataclass
class DimensionContribution:
    dimension: str
    value: Any
    metric_value: float
    contribution: float
    contribution_pct: float
    mom_pct: Optional[float] = None
    yoy_pct: Optional[float] = None
    is_anomaly: bool = False
    anomaly_direction: Optional[str] = None


@dataclass
class WaterfallItem:
    label: str
    value: float
    item_type: str


@dataclass
class DrilldownResult:
    metric_name: str
    dimensions: List[str]
    period: Tuple[Optional[datetime], Optional[datetime]]
    total_value: float
    total_mom_pct: Optional[float]
    contributions: Dict[str, List[DimensionContribution]] = field(default_factory=dict)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    waterfall: List[WaterfallItem] = field(default_factory=list)


class DrilldownEngine:
    def __init__(self, report_config: ReportConfig):
        self.config = report_config

    def _get_latest_period_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if "period" not in df.columns:
            return df
        latest_period = df["period"].max()
        return df[df["period"] == latest_period].copy()

    def _get_previous_period_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if "period" not in df.columns:
            return pd.DataFrame()
        periods = sorted(df["period"].unique())
        if len(periods) < 2:
            return pd.DataFrame()
        prev_period = periods[-2]
        return df[df["period"] == prev_period].copy()

    def _calculate_contributions(self, df: pd.DataFrame, dimension: str,
                                 total_value: float) -> List[DimensionContribution]:
        if dimension not in df.columns:
            logger.warning(f"Dimension '{dimension}' not found in data")
            return []

        dim_df = df.groupby(dimension, dropna=False)["metric_value"].sum().reset_index()
        dim_df = dim_df.sort_values("metric_value", ascending=False)

        if self.config.top_n:
            dim_df = dim_df.head(self.config.top_n)

        contributions = []
        for _, row in dim_df.iterrows():
            val = row["metric_value"]
            pct = (val / total_value * 100) if total_value != 0 else 0

            mom_pct = None
            yoy_pct = None
            is_anomaly = False
            direction = None

            if "mom_1_pct" in row.index:
                mom_pct = row["mom_1_pct"]
                if abs(mom_pct) >= self.config.anomaly_threshold * 100:
                    is_anomaly = True
                    direction = "up" if mom_pct > 0 else "down"

            if "yoy_pct" in row.index:
                yoy_pct = row["yoy_pct"]

            contributions.append(DimensionContribution(
                dimension=dimension,
                value=row[dimension],
                metric_value=float(val),
                contribution=float(val),
                contribution_pct=float(pct),
                mom_pct=float(mom_pct) if mom_pct is not None else None,
                yoy_pct=float(yoy_pct) if yoy_pct is not None else None,
                is_anomaly=is_anomaly,
                anomaly_direction=direction
            ))

        return contributions

    def _build_waterfall(self, current_df: pd.DataFrame, previous_df: pd.DataFrame,
                         dimensions: List[str],
                         current_total: float, previous_total: float) -> List[WaterfallItem]:
        waterfall = []

        waterfall.append(WaterfallItem(
            label="上期总额",
            value=float(previous_total),
            item_type="base"
        ))

        for dim in dimensions:
            if dim not in current_df.columns or dim not in previous_df.columns:
                continue

            curr_group = current_df.groupby(dim, dropna=False)["metric_value"].sum()
            prev_group = previous_df.groupby(dim, dropna=False)["metric_value"].sum()

            diff = (curr_group - prev_group).fillna(0)
            total_diff = diff.sum()

            if abs(total_diff) < 0.01:
                continue

            top_contributor = diff.idxmax()
            bottom_contributor = diff.idxmin()

            if diff.loc[top_contributor] > 0:
                waterfall.append(WaterfallItem(
                    label=f"{dim}: {top_contributor} 拉升",
                    value=float(diff.loc[top_contributor]),
                    item_type="increase"
                ))

            if diff.loc[bottom_contributor] < 0:
                waterfall.append(WaterfallItem(
                    label=f"{dim}: {bottom_contributor} 拖累",
                    value=float(diff.loc[bottom_contributor]),
                    item_type="decrease"
                ))

        other_diff = current_total - previous_total - sum(
            item.value for item in waterfall if item.item_type in ("increase", "decrease")
        )

        if abs(other_diff) > 0.01:
            waterfall.append(WaterfallItem(
                label="其他因素",
                value=float(other_diff),
                item_type="increase" if other_diff > 0 else "decrease"
            ))

        waterfall.append(WaterfallItem(
            label="本期总额",
            value=float(current_total),
            item_type="total"
        ))

        return waterfall

    def _detect_anomalies(self, contributions: Dict[str, List[DimensionContribution]]) -> List[Dict[str, Any]]:
        anomalies = []
        for dim, contribs in contributions.items():
            for c in contribs:
                if c.is_anomaly:
                    anomalies.append({
                        "dimension": dim,
                        "value": c.value,
                        "metric_value": c.metric_value,
                        "mom_pct": c.mom_pct,
                        "direction": c.anomaly_direction,
                        "contribution_pct": c.contribution_pct
                    })
        return sorted(anomalies, key=lambda x: abs(x.get("mom_pct", 0) or 0), reverse=True)

    def analyze(self, metric_result: MetricResult,
                start_date: Optional[datetime] = None,
                end_date: Optional[datetime] = None) -> DrilldownResult:
        df = metric_result.values.copy()

        if start_date and "period" in df.columns:
            df = df[df["period"] >= pd.to_datetime(start_date)]
        if end_date and "period" in df.columns:
            df = df[df["period"] <= pd.to_datetime(end_date)]

        current_df = self._get_latest_period_df(df)
        previous_df = self._get_previous_period_df(df)

        current_total = float(current_df["metric_value"].sum())
        previous_total = float(previous_df["metric_value"].sum()) if not previous_df.empty else None

        total_mom_pct = None
        if previous_total and previous_total > 0:
            total_mom_pct = (current_total - previous_total) / previous_total * 100

        dimensions_to_analyze = [
            d for d in self.config.drilldown_dimensions
            if d in current_df.columns
        ]

        contributions = {}
        for dim in dimensions_to_analyze:
            contributions[dim] = self._calculate_contributions(current_df, dim, current_total)

        anomalies = self._detect_anomalies(contributions)

        waterfall = []
        if not previous_df.empty and dimensions_to_analyze:
            waterfall = self._build_waterfall(
                current_df, previous_df, dimensions_to_analyze,
                current_total, previous_total
            )

        return DrilldownResult(
            metric_name=metric_result.metric_name,
            dimensions=dimensions_to_analyze,
            period=(start_date, end_date),
            total_value=current_total,
            total_mom_pct=total_mom_pct,
            contributions=contributions,
            anomalies=anomalies,
            waterfall=waterfall
        )

    def drilldown_to_subcategory(self, metric_result: MetricResult,
                                 parent_dimension: str,
                                 parent_value: Any,
                                 sub_dimension: str) -> List[DimensionContribution]:
        df = metric_result.values.copy()
        df = self._get_latest_period_df(df)

        if parent_dimension not in df.columns:
            logger.warning(f"Parent dimension '{parent_dimension}' not found")
            return []

        filtered = df[df[parent_dimension] == parent_value]
        total = float(filtered["metric_value"].sum())

        return self._calculate_contributions(filtered, sub_dimension, total)

    def to_dict(self, result: DrilldownResult) -> Dict[str, Any]:
        contrib_dict = {}
        for dim, contribs in result.contributions.items():
            contrib_dict[dim] = [
                {
                    "dimension": c.dimension,
                    "value": str(c.value) if c.value is not None else "NULL",
                    "metric_value": c.metric_value,
                    "contribution": c.contribution,
                    "contribution_pct": round(c.contribution_pct, 2),
                    "mom_pct": round(c.mom_pct, 2) if c.mom_pct is not None else None,
                    "yoy_pct": round(c.yoy_pct, 2) if c.yoy_pct is not None else None,
                    "is_anomaly": c.is_anomaly,
                    "anomaly_direction": c.anomaly_direction
                }
                for c in contribs
            ]

        return {
            "metric_name": result.metric_name,
            "dimensions": result.dimensions,
            "total_value": round(result.total_value, 2),
            "total_mom_pct": round(result.total_mom_pct, 2) if result.total_mom_pct is not None else None,
            "contributions": contrib_dict,
            "anomalies": [
                {
                    **a,
                    "mom_pct": round(a["mom_pct"], 2) if a.get("mom_pct") is not None else None,
                    "contribution_pct": round(a["contribution_pct"], 2)
                }
                for a in result.anomalies
            ],
            "waterfall": [
                {
                    "label": w.label,
                    "value": round(w.value, 2),
                    "type": w.item_type
                }
                for w in result.waterfall
            ]
        }
