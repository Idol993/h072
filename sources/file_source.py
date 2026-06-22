import pandas as pd
import os
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class FileSource:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._validate_file()

    def _validate_file(self) -> None:
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        ext = os.path.splitext(self.file_path)[1].lower()
        supported = [".csv", ".parquet", ".xlsx", ".xls"]
        if ext not in supported:
            raise ValueError(f"Unsupported file format: {ext}. Supported: {supported}")

    def get_file_mtime(self) -> datetime:
        mtime = os.path.getmtime(self.file_path)
        return datetime.fromtimestamp(mtime)

    def needs_refresh(self, last_fetch_time: Optional[datetime] = None) -> bool:
        if not last_fetch_time:
            return True
        return self.get_file_mtime() > last_fetch_time

    def read(self, **kwargs) -> pd.DataFrame:
        ext = os.path.splitext(self.file_path)[1].lower()
        logger.info(f"Reading {ext} file: {self.file_path}")

        if ext == ".csv":
            return self._read_csv(**kwargs)
        elif ext == ".parquet":
            return self._read_parquet(**kwargs)
        elif ext in [".xlsx", ".xls"]:
            return self._read_excel(**kwargs)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _read_csv(self, **kwargs) -> pd.DataFrame:
        default_kwargs = {
            "parse_dates": True
        }
        default_kwargs.update(kwargs)
        return pd.read_csv(self.file_path, **default_kwargs)

    def _read_parquet(self, **kwargs) -> pd.DataFrame:
        return pd.read_parquet(self.file_path, **kwargs)

    def _read_excel(self, **kwargs) -> pd.DataFrame:
        default_kwargs = {
            "engine": "openpyxl"
        }
        default_kwargs.update(kwargs)
        return pd.read_excel(self.file_path, **default_kwargs)

    def incremental_read(self, updated_at_field: str = "updated_at",
                         last_fetch_time: Optional[datetime] = None,
                         **kwargs) -> pd.DataFrame:
        df = self.read(**kwargs)

        if last_fetch_time and updated_at_field in df.columns:
            df[updated_at_field] = pd.to_datetime(df[updated_at_field])
            df = df[df[updated_at_field] > last_fetch_time]
            logger.info(f"Incremental read: {len(df)} new rows since {last_fetch_time}")

        return df


def detect_file_format(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    format_map = {
        ".csv": "csv",
        ".parquet": "parquet",
        ".xlsx": "excel",
        ".xls": "excel"
    }
    return format_map.get(ext, "unknown")
