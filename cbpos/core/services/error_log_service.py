"""
Error log reader service for Admin Tools.

Parses the rotating log files written by setup_logging() in main.py.
Log format: %(asctime)s | %(levelname)-8s | %(name)s | %(message)s
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from cbpos.config import Config

logger = logging.getLogger(__name__)


class ErrorLogService:
    """Read, filter, and export application log files."""

    LOG_DIR = Config.BASE_DIR / "logs"
    LOG_NAME = "cbpos.log"

    @classmethod
    def get_log_files(cls) -> List[Path]:
        """
        Return all log files (main + rotated), newest first.

        Rotated files are named cbpos.log.1, cbpos.log.2, etc.
        """
        if not cls.LOG_DIR.exists():
            return []
        files = sorted(cls.LOG_DIR.glob(f"{cls.LOG_NAME}*"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    @classmethod
    def read_logs(
        cls,
        level: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        max_entries: int = 500,
    ) -> List[Dict[str, str]]:
        """
        Read and filter log entries from all log files.

        Args:
            level: Filter by log level (WARNING, ERROR, CRITICAL). None = all.
            date_from: Only entries on or after this date.
            date_to: Only entries on or before this date.
            search: Case-insensitive substring search in message/source.
            max_entries: Maximum entries to return.

        Returns:
            List of dicts with keys: timestamp, level, source, message.
            Newest entries first.
        """
        entries: List[Dict[str, str]] = []

        for log_file in cls.get_log_files():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        parsed = cls._parse_line(line)
                        if parsed is None:
                            continue

                        # Level filter
                        if level and parsed["level"] != level:
                            continue

                        # Date filters
                        try:
                            entry_dt = datetime.strptime(parsed["timestamp"][:19], "%Y-%m-%d %H:%M:%S")
                            if date_from and entry_dt.date() < date_from.date():
                                continue
                            if date_to and entry_dt.date() > date_to.date():
                                continue
                        except (ValueError, IndexError):
                            pass

                        # Search filter
                        if search:
                            search_lower = search.lower()
                            if (
                                search_lower not in parsed["source"].lower()
                                and search_lower not in parsed["message"].lower()
                            ):
                                continue

                        entries.append(parsed)
            except Exception as e:
                logger.debug("Could not read log file %s: %s", log_file, e)

        # Sort by timestamp descending (newest first)
        entries.sort(key=lambda e: e["timestamp"], reverse=True)
        return entries[:max_entries]

    @classmethod
    def get_log_stats(cls) -> Dict[str, int]:
        """
        Count log entries by level.

        Returns:
            Dict with keys: WARNING, ERROR, CRITICAL and their counts.
        """
        stats: Dict[str, int] = {"WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        for log_file in cls.get_log_files():
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        parsed = cls._parse_line(line)
                        if parsed and parsed["level"] in stats:
                            stats[parsed["level"]] += 1
            except Exception as e:
                logger.debug("Could not get stats from log file %s: %s", log_file, e)
        return stats

    @classmethod
    def export_logs(cls, filepath: str, entries: List[Dict[str, str]]) -> None:
        """
        Export log entries to a text file.

        Args:
            filepath: Destination file path.
            entries: List of parsed log entry dicts.
        """
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("CB POS Error Log Export\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Entries: {len(entries)}\n")
            f.write("=" * 80 + "\n\n")
            for entry in entries:
                f.write(f"{entry['timestamp']} | {entry['level']:<8} | " f"{entry['source']} | {entry['message']}\n")

    @classmethod
    def get_total_log_size(cls) -> str:
        """Return human-readable combined size of all log files."""
        total = sum(f.stat().st_size for f in cls.get_log_files() if f.exists())
        if total >= 1024 * 1024:
            return f"{total / (1024 * 1024):.1f} MB"
        return f"{total / 1024:.1f} KB"

    @classmethod
    def clear_logs(cls) -> None:
        """Truncate main log file and delete rotated files."""
        main_log = cls.LOG_DIR / cls.LOG_NAME
        if main_log.exists():
            main_log.write_text("")

        for f in cls.get_log_files():
            if f.name != cls.LOG_NAME:
                try:
                    f.unlink()
                except Exception as e:
                    logger.debug("Could not delete rotated log %s: %s", f, e)

    @classmethod
    def _parse_line(cls, line: str) -> Optional[Dict[str, str]]:
        """
        Parse a single log line into a dict.

        Expected format: 2026-02-28 10:30:00,123 | WARNING  | module.name | message
        """
        line = line.strip()
        if not line:
            return None

        parts = line.split(" | ", maxsplit=3)
        if len(parts) < 4:
            return None

        return {
            "timestamp": parts[0].strip(),
            "level": parts[1].strip(),
            "source": parts[2].strip(),
            "message": parts[3].strip(),
        }
