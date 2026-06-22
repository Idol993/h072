import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
from typing import Optional, Dict, Any
import hashlib
import logging

logger = logging.getLogger(__name__)


class DatabaseSource:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.engine = None
        self._connect()

    def _connect(self) -> None:
        try:
            self.engine = create_engine(self.connection_string)
            logger.info(f"Connected to database: {self.connection_string.split('@')[-1] if '@' in self.connection_string else self.connection_string}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def get_last_updated(self, table_name: str, updated_at_field: str = "updated_at") -> Optional[datetime]:
        try:
            query = text(f"SELECT MAX({updated_at_field}) as last_update FROM {table_name}")
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                if result and result[0]:
                    return pd.to_datetime(result[0])
                return None
        except Exception as e:
            logger.warning(f"Could not get last updated time: {e}")
            return None

    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        try:
            logger.info(f"Executing query: {query[:100]}...")
            df = pd.read_sql(text(query), self.engine, params=params)
            logger.info(f"Query returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    def fetch_table(self, table_name: str, columns: Optional[list] = None,
                    since: Optional[datetime] = None,
                    updated_at_field: str = "updated_at") -> pd.DataFrame:
        col_str = ", ".join(columns) if columns else "*"
        query = f"SELECT {col_str} FROM {table_name}"

        params = {}
        if since:
            query += f" WHERE {updated_at_field} > :since"
            params["since"] = since

        return self.execute_query(query, params)

    def incremental_fetch(self, table_name: str,
                          columns: Optional[list] = None,
                          last_fetch_time: Optional[datetime] = None,
                          updated_at_field: str = "updated_at") -> pd.DataFrame:
        return self.fetch_table(
            table_name=table_name,
            columns=columns,
            since=last_fetch_time,
            updated_at_field=updated_at_field
        )

    def close(self) -> None:
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_query_hash(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()[:16]
