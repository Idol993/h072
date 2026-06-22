import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
import logging
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


class ReportRenderer:
    def __init__(self, template_dir: str = "./templates"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True
        )

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Template rendering failed: {e}")
            raise

    def render_report(self, report_data: Dict[str, Any],
                    output_path: str,
                    template_name: str = "report_template.html") -> str:
        context = {
            "report_data_json": json.dumps(report_data, ensure_ascii=False, default=str),
            "title": report_data.get("title", "Analytics Report"),
            "generated_at": report_data.get("generated_at", datetime.now().isoformat()),
            "metric_label": report_data.get("metric", {}).get("label", ""),
            "total_value": report_data.get("metric", {}).get("total_value", 0),
            "total_mom_pct": report_data.get("metric", {}).get("total_mom_pct"),
            "year": datetime.now().year
        }

        html_content = self.render(template_name, context)

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Report rendered to: {output_path}")
        return output_path
