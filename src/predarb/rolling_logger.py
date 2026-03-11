"""
Rolling Logger utility for prediction market arbitrage pipeline.

Provides step-specific logging with automatic line rotation.
Each pipeline step gets its own log file in the log/ directory.
Log files automatically rotate by removing the oldest line when exceeding 100 lines.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional


class RollingLogger:
    """
    Thread-safe rolling logger for pipeline steps.
    
    Features:
    - Separate log file per pipeline step
    - Automatic 100-line rotation (FIFO)
    - Timestamped entries with log levels
    - Thread-safe file operations
    """
    
    MAX_LINES = 100
    LOG_DIR = Path("log")
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the rolling logger.
        
        Args:
            base_dir: Base directory for log files (defaults to project root 'log/')
        """
        if base_dir:
            self.log_dir = Path(base_dir)
        else:
            self.log_dir = self.LOG_DIR
        
        # Create log directory if it doesn't exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread lock for safe concurrent writes
        self._lock = threading.Lock()
    
    def _get_log_path(self, step_name: str) -> Path:
        """Get the path for a step's log file."""
        # Sanitize step name for filesystem
        safe_name = step_name.lower().replace(" ", "_").replace("-", "_")
        return self.log_dir / f"{safe_name}.log"
    
    def _rotate_if_needed(self, log_path: Path) -> None:
        """
        Rotate log file if it exceeds MAX_LINES.
        
        Removes the oldest (first) line when the file has 100+ lines.
        """
        if not log_path.exists():
            return
        
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # If we're at or over the limit, remove the first line
            if len(lines) >= self.MAX_LINES:
                with open(log_path, "w", encoding="utf-8") as f:
                    # Keep all but the first line
                    f.writelines(lines[1:])
        except Exception as e:
            # Fail gracefully - don't crash the pipeline for logging issues
            print(f"Warning: Failed to rotate log {log_path}: {e}")
    
    def log(self, step_name: str, message: str, level: str = "INFO") -> None:
        """
        Log a message to the specified step's log file.
        
        Args:
            step_name: Name of the pipeline step (e.g., "FETCH", "TAG_FILTER")
            message: Log message
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        with self._lock:
            log_path = self._get_log_path(step_name)
            
            # Rotate before writing if needed
            self._rotate_if_needed(log_path)
            
            # Format log entry with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] [{level}] {message}\n"
            
            try:
                # Append the new log entry
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)
            except Exception as e:
                # Fail gracefully
                print(f"Warning: Failed to write to log {log_path}: {e}")
    
    def info(self, step_name: str, message: str) -> None:
        """Log an INFO message."""
        self.log(step_name, message, "INFO")
    
    def warning(self, step_name: str, message: str) -> None:
        """Log a WARNING message."""
        self.log(step_name, message, "WARNING")
    
    def error(self, step_name: str, message: str) -> None:
        """Log an ERROR message."""
        self.log(step_name, message, "ERROR")
    
    def debug(self, step_name: str, message: str) -> None:
        """Log a DEBUG message."""
        self.log(step_name, message, "DEBUG")
    
    def get_recent_logs(self, step_name: str, num_lines: int = 20) -> list[str]:
        """
        Retrieve the most recent log entries for a step.
        
        Args:
            step_name: Name of the pipeline step
            num_lines: Number of recent lines to retrieve
            
        Returns:
            List of recent log lines
        """
        log_path = self._get_log_path(step_name)
        
        if not log_path.exists():
            return []
        
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return lines[-num_lines:]
        except Exception as e:
            print(f"Warning: Failed to read log {log_path}: {e}")
            return []


# Global singleton instance for convenience
_global_logger: Optional[RollingLogger] = None


def get_logger() -> RollingLogger:
    """
    Get the global rolling logger instance.
    
    Creates a singleton instance on first call.
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = RollingLogger()
    return _global_logger
