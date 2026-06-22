import click
import os
import sys
import logging
from datetime import datetime
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.loader import load_config, AppConfig
from sources.db_source import DatabaseSource
from sources.file_source import FileSource
from sources.sheets_source import GoogleSheetsSource
from engine.cache import ParquetCache
from engine.metrics import MetricsEngine
from engine.drilldown import DrilldownEngine
from report.builder import ReportBuilder
from report.renderer import ReportRenderer
from scheduler import ReportScheduler, parse_schedule_arg


def load_data_from_source(config: AppConfig, cache: ParquetCache, source_name: Optional[str] = None):
    import pandas as pd

    source = config.sources[0] if source_name is None else config.get_source(source_name)
    if not source:
        raise ValueError(f"Source '{source_name}' not found in config")

    cache_key = f"source_{source.name}"
    cached = cache.get(cache_key)

    last_updated = None
    needs_refresh = False

    if source.type == "database":
        with DatabaseSource(source.connection_string) as db:
            last_updated = db.get_last_updated(
                source.table_name, source.updated_at_field
            ) if source.table_name else None
            needs_refresh = cache.needs_refresh(cache_key, {}, last_updated)

            if needs_refresh or cached is None:
                if source.query:
                    df = db.execute_query(source.query)
                elif source.table_name:
                    df = db.incremental_fetch(
                        source.table_name,
                        updated_at_field=source.updated_at_field,
                        last_fetch_time=cache.metadata.get(cache_key, {}).get("source_last_updated")
                    )
                else:
                    raise ValueError("Database source must have either query or table_name")
            else:
                return cached

    elif source.type == "file":
        file_source = FileSource(source.file_path)
        last_updated = file_source.get_file_mtime()
        needs_refresh = cache.needs_refresh(cache_key, {}, last_updated)

        if needs_refresh or cached is None:
            df = file_source.incremental_read(
                updated_at_field=source.updated_at_field,
                last_fetch_time=cache.metadata.get(cache_key, {}).get("source_last_updated")
            )
        else:
            return cached

    elif source.type == "google_sheets":
        sheets = GoogleSheetsSource(
            source.sheet_id,
            credentials_path=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        )
        last_updated = sheets.get_last_updated(
            source.sheet_range or "Sheet1", source.updated_at_field
        )
        needs_refresh = cache.needs_refresh(cache_key, {}, last_updated)

        if needs_refresh or cached is None:
            df = sheets.incremental_read(
                source.sheet_range or "Sheet1",
                updated_at_field=source.updated_at_field,
                last_fetch_time=cache.metadata.get(cache_key, {}).get("source_last_updated")
            )
        else:
            return cached

    else:
        raise ValueError(f"Unsupported source type: {source.type}")

    if cached is not None and len(cached) > 0 and len(df) > 0:
        df = pd.concat([cached, df], ignore_index=True)
        df = df.drop_duplicates(keep="last")

    cache.put(cache_key, df, {}, last_updated)
    return df


def generate_report(config: AppConfig, metric_name: str,
                   report_name: Optional[str] = None,
                   time_grain: str = "day",
                   output_dir: Optional[str] = None) -> str:
    output_dir = output_dir or config.output_dir
    os.makedirs(output_dir, exist_ok=True)

    cache = ParquetCache(config.cache_dir)

    logger.info("Loading data...")
    df = load_data_from_source(config, cache)
    logger.info(f"Loaded {len(df)} rows of data")

    metric_config = config.get_metric(metric_name)
    if not metric_config:
        raise ValueError(f"Metric '{metric_name}' not found in config")

    report_config = config.reports[0] if report_name is None else next(
        (r for r in config.reports if r.title == report_name), None
    )
    if not report_config:
        raise ValueError(f"Report '{report_name}' not found in config")

    logger.info(f"Calculating metric: {metric_config.label}")
    metrics_engine = MetricsEngine(df, metric_config.timestamp)
    all_dims = list(dict.fromkeys(report_config.dimensions + report_config.drilldown_dimensions))
    metric_result = metrics_engine.calculate_full_metric(
        metric_config,
        time_grain=time_grain,
        dimensions=all_dims,
        yoy=True,
        mom=True,
        moving_average_windows=report_config.moving_average_windows
    )

    logger.info("Building drilldown analysis...")
    drilldown_engine = DrilldownEngine(report_config)
    drilldown_result = drilldown_engine.analyze(metric_result)

    logger.info("Generating report data...")
    builder = ReportBuilder(report_config)
    report_data = builder.build_full_report(metric_result, drilldown_result)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(
        output_dir,
        f"{metric_name}_report_{timestamp}.html"
    )

    logger.info("Rendering HTML report...")
    renderer = ReportRenderer("./templates")
    renderer.render_report(report_data, output_path)

    logger.info(f"Report generated: {output_path}")
    return output_path


@click.group()
def cli():
    """电商运营指标多维下钻分析与自动报告工具"""
    pass


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
@click.option("--metric", "-m", required=True, help="指标名称")
@click.option("--report", "-r", help="报告名称")
@click.option("--time-grain", "-t", default="day",
              type=click.Choice(["day", "week", "month", "quarter", "year"]),
              help="时间粒度")
@click.option("--output", "-o", help="输出目录")
@click.option("--force-refresh", is_flag=True, help="强制刷新缓存")
def generate(config, metric, report, time_grain, output, force_refresh):
    """生成分析报告"""
    try:
        app_config = load_config(config)

        if force_refresh:
            cache = ParquetCache(app_config.cache_dir)
            cache.clear_all()
            logger.info("Cache cleared")

        report_path = generate_report(
            app_config, metric, report, time_grain, output
        )
        click.echo(f"✅ 报告生成成功: {report_path}")

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
@click.option("--metric", "-m", required=True, help="指标名称")
@click.option("--schedule", "-s", help="调度配置，格式: daily@09:00")
@click.option("--time-grain", "-t", default="day",
              type=click.Choice(["day", "week", "month", "quarter", "year"]),
              help="时间粒度")
def run(config, metric, schedule, time_grain):
    """运行单次报告或启动定时调度"""
    try:
        app_config = load_config(config)

        def report_gen():
            return generate_report(app_config, metric, None, time_grain)

        if schedule:
            scheduler = ReportScheduler(app_config, report_gen)
            scheduler.start(schedule)
        else:
            report_path = report_gen()
            click.echo(f"✅ 报告生成成功: {report_path}")

    except Exception as e:
        logger.error(f"Execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
@click.option("--clear", is_flag=True, help="清空缓存")
@click.option("--info", is_flag=True, help="显示缓存信息")
def cache(config, clear, info):
    """缓存管理"""
    app_config = load_config(config)
    cache = ParquetCache(app_config.cache_dir)

    if clear:
        cache.clear_all()
        click.echo("✅ 缓存已清空")
    elif info:
        info_data = cache.get_cache_info()
        click.echo(f"缓存条目数: {info_data['entry_count']}")
        click.echo(f"总大小: {info_data['total_size_mb']:.2f} MB")
        for key, meta in info_data["entries"].items():
            click.echo(f"  - {key}: {meta['row_count']} rows, created at {meta['created_at']}")
    else:
        click.echo("请使用 --clear 或 --info 参数")


@cli.command()
@click.option("--config", "-c", default="config.yaml", help="配置文件路径")
def validate(config):
    """验证配置文件"""
    try:
        app_config = load_config(config)
        click.echo("✅ 配置文件验证通过")
        click.echo(f"数据源: {len(app_config.sources)} 个")
        click.echo(f"指标: {len(app_config.metrics)} 个")
        for m in app_config.metrics:
            click.echo(f"  - {m.name}: {m.label} ({m.formula})")
        click.echo(f"报告: {len(app_config.reports)} 个")
        for r in app_config.reports:
            click.echo(f"  - {r.title}: 指标={r.metrics}, 维度={r.dimensions}")
        if app_config.schedule.enabled:
            click.echo(f"调度: {app_config.schedule.frequency}@{app_config.schedule.time}")
            click.echo(f"收件人: {app_config.schedule.recipients}")
    except Exception as e:
        click.echo(f"❌ 配置验证失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
