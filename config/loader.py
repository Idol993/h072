import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import os


@dataclass
class MetricFilter:
    field: str
    operator: str
    value: Any


@dataclass
class MetricConfig:
    name: str
    label: str
    description: str = ""
    calculation_method: str = "sum"
    expression: str = ""
    timestamp: str = "order_date"
    time_grains: List[str] = field(default_factory=lambda: ["day", "week", "month"])
    dimensions: List[str] = field(default_factory=list)
    filters: List[MetricFilter] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def formula(self) -> str:
        filter_str = ""
        if self.filters:
            conditions = []
            for f in self.filters:
                conditions.append(f"{f.field} {f.operator} {f.value}")
            filter_str = f" where {' and '.join(conditions)}"
        return f"{self.calculation_method}({self.expression}){filter_str}"


@dataclass
class SourceConfig:
    type: str
    name: str
    connection_string: Optional[str] = None
    file_path: Optional[str] = None
    sheet_id: Optional[str] = None
    sheet_range: Optional[str] = None
    table_name: Optional[str] = None
    query: Optional[str] = None
    updated_at_field: str = "updated_at"


@dataclass
class ReportConfig:
    title: str
    metrics: List[str]
    dimensions: List[str]
    drilldown_dimensions: List[str]
    anomaly_threshold: float = 0.15
    top_n: int = 10
    moving_average_windows: List[int] = field(default_factory=lambda: [7, 30])


@dataclass
class ScheduleConfig:
    enabled: bool = False
    frequency: str = "daily"
    time: str = "09:00"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    recipients: List[str] = field(default_factory=list)
    sender: str = ""


@dataclass
class AppConfig:
    sources: List[SourceConfig]
    metrics: List[MetricConfig]
    reports: List[ReportConfig]
    schedule: ScheduleConfig
    cache_dir: str = "./cache"
    output_dir: str = "./output"

    def get_metric(self, name: str) -> Optional[MetricConfig]:
        for m in self.metrics:
            if m.name == name:
                return m
        return None

    def get_source(self, name: str) -> Optional[SourceConfig]:
        for s in self.sources:
            if s.name == name:
                return s
        return None


def parse_filters(filters_data: Optional[List[Dict]]) -> List[MetricFilter]:
    if not filters_data:
        return []
    result = []
    for f in filters_data:
        result.append(MetricFilter(
            field=f.get("field", ""),
            operator=f.get("operator", "="),
            value=f.get("value", "")
        ))
    return result


def load_config(config_path: str) -> AppConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    sources_data = data.get("sources", [])
    metrics_data = data.get("metrics", [])
    reports_data = data.get("reports", [])
    schedule_data = data.get("schedule", {})

    sources = []
    for s in sources_data:
        sources.append(SourceConfig(
            type=s.get("type", ""),
            name=s.get("name", ""),
            connection_string=s.get("connection_string"),
            file_path=s.get("file_path"),
            sheet_id=s.get("sheet_id"),
            sheet_range=s.get("sheet_range"),
            table_name=s.get("table_name"),
            query=s.get("query"),
            updated_at_field=s.get("updated_at_field", "updated_at")
        ))

    metrics = []
    for m in metrics_data:
        metrics.append(MetricConfig(
            name=m.get("name", ""),
            label=m.get("label", m.get("name", "")),
            description=m.get("description", ""),
            calculation_method=m.get("calculation_method", "sum"),
            expression=m.get("expression", ""),
            timestamp=m.get("timestamp", "order_date"),
            time_grains=m.get("time_grains", ["day", "week", "month"]),
            dimensions=m.get("dimensions", []),
            filters=parse_filters(m.get("filters", [])),
            meta=m.get("meta", {})
        ))

    reports = []
    for r in reports_data:
        reports.append(ReportConfig(
            title=r.get("title", "Analytics Report"),
            metrics=r.get("metrics", []),
            dimensions=r.get("dimensions", []),
            drilldown_dimensions=r.get("drilldown_dimensions", []),
            anomaly_threshold=r.get("anomaly_threshold", 0.15),
            top_n=r.get("top_n", 10),
            moving_average_windows=r.get("moving_average_windows", [7, 30])
        ))

    schedule = ScheduleConfig(
        enabled=schedule_data.get("enabled", False),
        frequency=schedule_data.get("frequency", "daily"),
        time=schedule_data.get("time", "09:00"),
        smtp_host=schedule_data.get("smtp_host", ""),
        smtp_port=schedule_data.get("smtp_port", 587),
        smtp_user=schedule_data.get("smtp_user", ""),
        smtp_password=schedule_data.get("smtp_password", ""),
        smtp_use_tls=schedule_data.get("smtp_use_tls", True),
        recipients=schedule_data.get("recipients", []),
        sender=schedule_data.get("sender", "")
    )

    return AppConfig(
        sources=sources,
        metrics=metrics,
        reports=reports,
        schedule=schedule,
        cache_dir=data.get("cache_dir", "./cache"),
        output_dir=data.get("output_dir", "./output")
    )
