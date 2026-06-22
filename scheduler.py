import os
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Callable, Dict, Any

from config.loader import AppConfig, ScheduleConfig

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not available. Scheduling functionality will be limited.")


class EmailSender:
    def __init__(self, schedule_config: ScheduleConfig):
        self.config = schedule_config

    def send_report(self, subject: str, body: str,
                   attachments: Optional[List[str]] = None) -> bool:
        if not self.config.smtp_host:
            logger.error("SMTP host not configured")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.config.sender or self.config.smtp_user
            msg["To"] = ", ".join(self.config.recipients)
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "html", "utf-8"))

            if attachments:
                for file_path in attachments:
                    if not os.path.exists(file_path):
                        logger.warning(f"Attachment not found: {file_path}")
                        continue

                    with open(file_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())

                    encoders.encode_base64(part)
                    filename = os.path.basename(file_path)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename= {filename}"
                    )
                    msg.attach(part)

            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.smtp_use_tls:
                    server.starttls()
                if self.config.smtp_user and self.config.smtp_password:
                    server.login(self.config.smtp_user, self.config.smtp_password)

                server.send_message(msg)

            logger.info(f"Email sent to {len(self.config.recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class ReportScheduler:
    def __init__(self, app_config: AppConfig,
                 report_generator: Callable[[], str]):
        self.config = app_config
        self.report_generator = report_generator
        self.scheduler = None
        self.email_sender = EmailSender(app_config.schedule)

    def _parse_schedule(self, schedule_str: str) -> Dict[str, str]:
        parts = schedule_str.split("@")
        if len(parts) != 2:
            raise ValueError(f"Invalid schedule format: {schedule_str}. Use format: daily@09:00")

        frequency, time_str = parts[0].strip().lower(), parts[1].strip()
        time_parts = time_str.split(":")

        if len(time_parts) != 2:
            raise ValueError(f"Invalid time format: {time_str}. Use HH:MM")

        hour, minute = time_parts[0], time_parts[1]

        cron_kwargs = {"hour": hour, "minute": minute}

        if frequency == "daily":
            pass
        elif frequency == "weekly":
            cron_kwargs["day_of_week"] = "mon"
        elif frequency == "monthly":
            cron_kwargs["day"] = "1"
        elif frequency.startswith("every"):
            try:
                interval = int(frequency.replace("every", "").strip())
                cron_kwargs = {"trigger": "interval", "minutes": interval}
            except ValueError:
                raise ValueError(f"Invalid interval: {frequency}")
        else:
            raise ValueError(f"Unsupported frequency: {frequency}")

        return cron_kwargs

    def run_report_and_send(self) -> None:
        logger.info("Running scheduled report generation...")
        try:
            report_path = self.report_generator()

            if report_path and self.config.schedule.recipients:
                subject = f"GMV分析周报 - {datetime.now().strftime('%Y-%m-%d')}"
                body = f"""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>GMV分析周报已生成</h2>
                    <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>请查看附件中的完整交互式报告。</p>
                    <br>
                    <p>此邮件由系统自动发送，请勿直接回复。</p>
                </body>
                </html>
                """

                self.email_sender.send_report(
                    subject=subject,
                    body=body,
                    attachments=[report_path]
                )

        except Exception as e:
            logger.error(f"Scheduled report failed: {e}")
            import traceback
            traceback.print_exc()

    def start(self, schedule_str: Optional[str] = None) -> None:
        if not APSCHEDULER_AVAILABLE:
            raise ImportError("APScheduler is required for scheduling. "
                            "Install with: pip install apscheduler")

        schedule_str = schedule_str or f"{self.config.schedule.frequency}@{self.config.schedule.time}"

        self.scheduler = BackgroundScheduler()

        cron_kwargs = self._parse_schedule(schedule_str)

        if cron_kwargs.get("trigger") == "interval":
            self.scheduler.add_job(
                self.run_report_and_send,
                "interval",
                minutes=cron_kwargs["minutes"],
                id="report_job",
                replace_existing=True
            )
        else:
            trigger = CronTrigger(**cron_kwargs)
            self.scheduler.add_job(
                self.run_report_and_send,
                trigger,
                id="report_job",
                replace_existing=True
            )

        self.scheduler.start()
        logger.info(f"Scheduler started with schedule: {schedule_str}")

        try:
            import time
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self) -> None:
        if self.scheduler:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")


def parse_schedule_arg(schedule_str: str) -> Dict[str, str]:
    parts = schedule_str.split("@")
    if len(parts) != 2:
        raise ValueError(f"Invalid schedule format: {schedule_str}. Use format: daily@09:00")

    frequency, time_str = parts[0].strip().lower(), parts[1].strip()
    return {"frequency": frequency, "time": time_str}
