import pandas as pd
import os
import hashlib
import json
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ParquetCache:
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = cache_dir
        self.metadata_file = os.path.join(cache_dir, "cache_metadata.json")
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self._ensure_cache_dir()
        self._load_metadata()

    def _ensure_cache_dir(self) -> None:
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info(f"Created cache directory: {self.cache_dir}")

    def _load_metadata(self) -> None:
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load cache metadata: {e}")
                self.metadata = {}

    def _save_metadata(self) -> None:
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Could not save cache metadata: {e}")

    def _get_cache_key(self, identifier: str, params: Optional[Dict] = None) -> str:
        if params:
            params_str = json.dumps(params, sort_keys=True, default=str)
            hash_suffix = hashlib.md5(params_str.encode()).hexdigest()[:8]
            return f"{identifier}_{hash_suffix}"
        return identifier

    def _get_cache_path(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, f"{cache_key}.parquet")

    def get(self, identifier: str, params: Optional[Dict] = None,
            max_age_seconds: Optional[int] = None) -> Optional[pd.DataFrame]:
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key)

        if not os.path.exists(cache_path):
            return None

        if max_age_seconds:
            mtime = os.path.getmtime(cache_path)
            age = datetime.now().timestamp() - mtime
            if age > max_age_seconds:
                logger.info(f"Cache expired for {cache_key} (age: {age:.0f}s)")
                return None

        try:
            df = pd.read_parquet(cache_path)
            logger.info(f"Loaded from cache: {cache_key} ({len(df)} rows)")
            return df
        except Exception as e:
            logger.warning(f"Could not read cache {cache_key}: {e}")
            return None

    def put(self, identifier: str, df: pd.DataFrame,
            params: Optional[Dict] = None,
            source_last_updated: Optional[datetime] = None) -> str:
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key)

        try:
            df.to_parquet(cache_path, index=False)
            logger.info(f"Cached {len(df)} rows to {cache_key}")

            self.metadata[cache_key] = {
                "identifier": identifier,
                "params": params,
                "created_at": datetime.now().isoformat(),
                "row_count": len(df),
                "source_last_updated": source_last_updated.isoformat() if source_last_updated else None,
                "file_path": cache_path
            }
            self._save_metadata()

            return cache_key
        except Exception as e:
            logger.error(f"Could not write cache {cache_key}: {e}")
            raise

    def needs_refresh(self, identifier: str, params: Optional[Dict] = None,
                      source_last_updated: Optional[datetime] = None) -> bool:
        cache_key = self._get_cache_key(identifier, params)

        if cache_key not in self.metadata:
            return True

        if not source_last_updated:
            return False

        cached_last_update = self.metadata[cache_key].get("source_last_updated")
        if not cached_last_update:
            return True

        try:
            cached_dt = datetime.fromisoformat(cached_last_update)
            return source_last_updated > cached_dt
        except Exception:
            return True

    def invalidate(self, identifier: str, params: Optional[Dict] = None) -> None:
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key)

        if os.path.exists(cache_path):
            os.remove(cache_path)
            logger.info(f"Invalidated cache: {cache_key}")

        if cache_key in self.metadata:
            del self.metadata[cache_key]
            self._save_metadata()

    def clear_all(self) -> None:
        for cache_key in list(self.metadata.keys()):
            cache_path = self.metadata[cache_key].get("file_path")
            if cache_path and os.path.exists(cache_path):
                os.remove(cache_path)

        self.metadata = {}
        self._save_metadata()
        logger.info("All cache cleared")

    def get_cache_info(self) -> Dict[str, Any]:
        total_size = 0
        for cache_key, info in self.metadata.items():
            path = info.get("file_path", "")
            if os.path.exists(path):
                total_size += os.path.getsize(path)

        return {
            "entry_count": len(self.metadata),
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "entries": self.metadata
        }
