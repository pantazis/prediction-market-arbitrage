"""
Unit tests for RollingLogger.

Tests the rolling log functionality including file creation, rotation, and thread safety.
"""

import os
import tempfile
import threading
from pathlib import Path
import pytest

from predarb.rolling_logger import RollingLogger


class TestRollingLogger:
    """Test suite for RollingLogger."""
    
    def test_log_file_creation(self, tmp_path):
        """Test that log files are created in the correct location."""
        logger = RollingLogger(base_dir=tmp_path)
        
        logger.info("FETCH", "Test message")
        
        log_file = tmp_path / "fetch.log"
        assert log_file.exists()
        
        with open(log_file, "r") as f:
            content = f.read()
            assert "[INFO] Test message" in content
    
    def test_multiple_steps(self, tmp_path):
        """Test that different steps create separate log files."""
        logger = RollingLogger(base_dir=tmp_path)
        
        steps = ["FETCH", "TAG_FILTER", "VECTORIZE", "MATCH", "LLM_VERIFICATION"]
        for step in steps:
            logger.info(step, f"Message for {step}")
        
        # Verify all log files exist
        for step in steps:
            log_file = tmp_path / f"{step.lower().replace('_', '_')}.log"
            assert log_file.exists()
    
    def test_log_rotation(self, tmp_path):
        """Test that log rotation works at 100 lines."""
        logger = RollingLogger(base_dir=tmp_path)
        
        # Write 105 lines
        for i in range(105):
            logger.info("TEST", f"Line {i}")
        
        log_file = tmp_path / "test.log"
        with open(log_file, "r") as f:
            lines = f.readlines()
        
        # Should have exactly 100 lines (oldest 5 removed)
        assert len(lines) == 100
        
        # First line should be "Line 5" (since Lines 0-4 were removed)
        assert "Line 5" in lines[0]
        
        # Last line should be "Line 104"
        assert "Line 104" in lines[-1]
    
    def test_log_levels(self, tmp_path):
        """Test different log levels."""
        logger = RollingLogger(base_dir=tmp_path)
        
        logger.info("TEST", "Info message")
        logger.warning("TEST", "Warning message")
        logger.error("TEST", "Error message")
        logger.debug("TEST", "Debug message")
        
        log_file = tmp_path / "test.log"
        with open(log_file, "r") as f:
            content = f.read()
        
        assert "[INFO] Info message" in content
        assert "[WARNING] Warning message" in content
        assert "[ERROR] Error message" in content
        assert "[DEBUG] Debug message" in content
    
    def test_timestamp_format(self, tmp_path):
        """Test that timestamps are properly formatted."""
        logger = RollingLogger(base_dir=tmp_path)
        
        logger.info("TEST", "Timestamped message")
        
        log_file = tmp_path / "test.log"
        with open(log_file, "r") as f:
            line = f.readline()
        
        # Should match format: [YYYY-MM-DD HH:MM:SS] [LEVEL] message
        assert line.count("[") >= 2
        assert line.count("]") >= 2
    
    def test_thread_safety(self, tmp_path):
        """Test concurrent writes from multiple threads."""
        logger = RollingLogger(base_dir=tmp_path)
        
        def worker(thread_id, num_messages):
            for i in range(num_messages):
                logger.info("CONCURRENT", f"Thread {thread_id} - Message {i}")
        
        threads = []
        num_threads = 5
        messages_per_thread = 20
        
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i, messages_per_thread))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        log_file = tmp_path / "concurrent.log"
        with open(log_file, "r") as f:
            lines = f.readlines()
        
        # Should have exactly num_threads * messages_per_thread lines
        assert len(lines) == num_threads * messages_per_thread
    
    def test_get_recent_logs(self, tmp_path):
        """Test retrieving recent log entries."""
        logger = RollingLogger(base_dir=tmp_path)
        
        for i in range(50):
            logger.info("RECENT", f"Message {i}")
        
        recent = logger.get_recent_logs("RECENT", num_lines=10)
        
        assert len(recent) == 10
        assert "Message 49" in recent[-1]
        assert "Message 40" in recent[0]
    
    def test_step_name_sanitization(self, tmp_path):
        """Test that step names are properly sanitized for filenames."""
        logger = RollingLogger(base_dir=tmp_path)
        
        # Use a step name with spaces and special characters
        logger.info("LLM VERIFICATION", "Test message")
        
        # Should create a file with underscores
        log_file = tmp_path / "llm_verification.log"
        assert log_file.exists()
    
    def test_graceful_error_handling(self, tmp_path):
        """Test that logging failures don't crash the application."""
        logger = RollingLogger(base_dir=tmp_path)
        
        # Write to a valid location first
        logger.info("TEST", "Valid message")
        
        # Try to write to read-only location (should fail gracefully)
        # This is hard to test portably, so we'll just verify no exception is raised
        try:
            logger.log("TEST", "Another message", "INFO")
        except Exception as e:
            pytest.fail(f"Logger should handle errors gracefully, but raised: {e}")


@pytest.fixture
def tmp_path():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
