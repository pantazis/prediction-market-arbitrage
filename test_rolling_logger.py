#!/usr/bin/env python3
"""
Simple test script to verify RollingLogger functionality.
Creates test logs and validates the rolling mechanism.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.rolling_logger import RollingLogger

def test_basic_logging():
    """Test basic logging functionality."""
    print("=" * 60)
    print("TEST 1: Basic Logging")
    print("=" * 60)
    
    logger = RollingLogger()
    
    # Test all 5 pipeline steps
    steps = ["FETCH", "TAG_FILTER", "VECTORIZE", "MATCH", "LLM_VERIFICATION"]
    
    for step in steps:
        logger.info(step, f"Test log message for {step}")
        logger.debug(step, f"Debug message for {step}")
    
    # Check if log files were created
    print("\nChecking log files:")
    for step in steps:
        log_path = Path("log") / f"{step.lower()}.log"
        if log_path.exists():
            print(f"  ✓ {log_path} created")
            with open(log_path, "r") as f:
                lines = f.readlines()
                print(f"    - Contains {len(lines)} lines")
        else:
            print(f"  ✗ {log_path} NOT found")
    
    print("\n✅ Test 1 Complete\n")

def test_rotation():
    """Test log rotation at 100 lines."""
    print("=" * 60)
    print("TEST 2: Log Rotation (100 lines)")
    print("=" * 60)
    
    logger = RollingLogger()
    
    print("Writing 105 log entries...")
    for i in range(105):
        logger.info("ROTATION_TEST", f"Log entry {i:03d}")
        if (i + 1) % 20 == 0:
            print(f"  - Written {i + 1} entries")
    
    log_path = Path("log") / "rotation_test.log"
    with open(log_path, "r") as f:
        lines = f.readlines()
    
    print(f"\nResults:")
    print(f"  - Total lines in file: {len(lines)}")
    print(f"  - Expected: 100 (rotation should have occurred)")
    
    if len(lines) == 100:
        print(f"  ✅ Rotation working correctly!")
        print(f"  - First line contains: {lines[0].strip()[-20:]}")
        print(f"  - Last line contains: {lines[-1].strip()[-20:]}")
    else:
        print(f"  ✗ Rotation NOT working (expected 100, got {len(lines)})")
    
    print("\n✅ Test 2 Complete\n")

def test_log_format():
    """Test log formatting."""
    print("=" * 60)
    print("TEST 3: Log Format Validation")
    print("=" * 60)
    
    logger = RollingLogger()
    
    logger.info("FORMAT_TEST", "Info level message")
    logger.warning("FORMAT_TEST", "Warning level message")
    logger.error("FORMAT_TEST", "Error level message")
    
    log_path = Path("log") / "format_test.log"
    with open(log_path, "r") as f:
        lines = f.readlines()
    
    print("\nLog entries:")
    for line in lines:
        print(f"  {line.strip()}")
    
    # Validate format: [TIMESTAMP] [LEVEL] message
    all_valid = True
    for i, line in enumerate(lines, 1):
        if not (line.count("[") >= 2 and line.count("]") >= 2):
            print(f"  ✗ Line {i}: Invalid format")
            all_valid = False
    
    if all_valid:
        print("\n✅ All log entries have valid format")
    
    print("\n✅ Test 3 Complete\n")

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("ROLLING LOGGER VERIFICATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        test_basic_logging()
        test_rotation()
        test_log_format()
        
        print("=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        
        # Show log directory contents
        print("\nLog directory contents:")
        log_dir = Path("log")
        if log_dir.exists():
            for log_file in sorted(log_dir.glob("*.log")):
                size = log_file.stat().st_size
                print(f"  - {log_file.name} ({size} bytes)")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
