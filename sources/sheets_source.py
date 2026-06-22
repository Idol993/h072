import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
import os

logger = logging.getLogger(__name__)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not available. Google Sheets functionality will be limited.")


class GoogleSheetsSource:
    def __init__(self, sheet_id: str, credentials_path: Optional[str] = None,
                 oauth2_credentials: Optional[Dict] = None):
        if not GSPREAD_AVAILABLE:
            raise ImportError("gspread is required for Google Sheets source. "
                            "Install with: pip install gspread google-auth google-auth-oauthlib")

        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.oauth2_credentials = oauth2_credentials
        self.client = None
        self._authenticate()

    def _authenticate(self) -> None:
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]

            if self.credentials_path and os.path.exists(self.credentials_path):
                creds = Credentials.from_service_account_file(
                    self.credentials_path, scopes=scopes
                )
            elif self.oauth2_credentials:
                from google.oauth2.credentials import Credentials as UserCreds
                creds = UserCreds.from_authorized_user_info(
                    self.oauth2_credentials, scopes=scopes
                )
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            else:
                raise ValueError("No credentials provided for Google Sheets")

            self.client = gspread.authorize(creds)
            logger.info("Authenticated with Google Sheets API")
        except Exception as e:
            logger.error(f"Google Sheets authentication failed: {e}")
            raise

    def get_last_updated(self, sheet_range: str = "Sheet1",
                         updated_at_field: str = "updated_at") -> Optional[datetime]:
        try:
            df = self.read_range(sheet_range)
            if updated_at_field in df.columns:
                last_update = pd.to_datetime(df[updated_at_field]).max()
                return last_update
            return None
        except Exception as e:
            logger.warning(f"Could not get last updated time: {e}")
            return None

    def read_range(self, range_name: str) -> pd.DataFrame:
        try:
            sheet = self.client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(range_name.split("!")[0])
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)

            for col in df.columns:
                if "date" in col.lower() or "time" in col.lower() or "updated_at" in col.lower():
                    df[col] = pd.to_datetime(df[col], errors="ignore")

            logger.info(f"Read {len(df)} rows from Google Sheets range: {range_name}")
            return df
        except Exception as e:
            logger.error(f"Failed to read Google Sheets: {e}")
            raise

    def incremental_read(self, range_name: str,
                         updated_at_field: str = "updated_at",
                         last_fetch_time: Optional[datetime] = None) -> pd.DataFrame:
        df = self.read_range(range_name)

        if last_fetch_time and updated_at_field in df.columns:
            df[updated_at_field] = pd.to_datetime(df[updated_at_field])
            df = df[df[updated_at_field] > last_fetch_time]
            logger.info(f"Incremental read: {len(df)} new rows since {last_fetch_time}")

        return df

    def list_worksheets(self) -> List[str]:
        try:
            sheet = self.client.open_by_key(self.sheet_id)
            return [ws.title for ws in sheet.worksheets()]
        except Exception as e:
            logger.error(f"Failed to list worksheets: {e}")
            raise


def save_oauth2_credentials(creds: Dict, path: str) -> None:
    import json
    with open(path, "w") as f:
        json.dump(creds, f)
    logger.info(f"OAuth2 credentials saved to {path}")
