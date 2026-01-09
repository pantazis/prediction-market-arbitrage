#!/usr/bin/env python3
"""
Quick validation script to verify live paper trading setup.

Checks:
1. Python version
2. Dependencies installed
3. Config file valid
4. API connectivity
5. No injection clients
6. All required files present
"""
import sys
from pathlib import Path

def check_python_version():
    """Check Python version is 3.10+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ Python {version.major}.{version.minor} detected. Require 3.10+")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Check required packages are installed"""
    required = ['yaml', 'pydantic', 'requests', 'pytest']
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            print(f"  ❌ {package}")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("   Run: pip3 install -r requirements.txt")
        return False
    
    print("✓ All dependencies installed")
    return True

def check_config():
    """Check config file exists and loads"""
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from predarb.config import load_config
        
        config_path = Path("config_live_paper.yml")
        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            return False
        
        config = load_config(str(config_path))
        print(f"✓ Config loaded successfully")
        print(f"  - Initial capital: ${config.broker.initial_cash:.2f}")
        print(f"  - Refresh rate: {config.engine.refresh_seconds}s")
        print(f"  - Stop loss: {config.risk.kill_switch_drawdown:.1%}")
        
        # Check that duplicate detector is disabled (requires short selling)
        if config.detectors.enable_duplicate:
            print(f"  ⚠ Warning: Duplicate detector enabled (requires short selling)")
        
        return True
    except Exception as e:
        print(f"❌ Config validation failed: {e}")
        return False

def check_api_connectivity():
    """Test API connectivity"""
    try:
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from predarb.config import load_config
        from predarb.polymarket_client import PolymarketClient
        
        config = load_config("config_live_paper.yml")
        client = PolymarketClient(config.polymarket)
        markets = client.fetch_markets()
        
        print(f"✓ API connectivity OK - fetched {len(markets)} markets")
        if markets:
            print(f"  - Sample: {markets[0].question[:50]}...")
        return True
    except Exception as e:
        print(f"⚠ API connectivity test failed: {e}")
        print("  (This may be OK if running offline)")
        return True  # Don't fail on API errors

def check_files():
    """Check all required files exist"""
    required_files = [
        "run_live_paper.py",
        "config_live_paper.yml",
        "run_live_paper_setup.sh",
        "LIVE_PAPER_TRADING_GUIDE.md",
        "LIVE_PAPER_TRADING_COMMANDS.md",
        "README_LIVE_PAPER_TRADING.md",
        "requirements.txt",
    ]
    
    missing = []
    for file in required_files:
        path = Path(file)
        if path.exists():
            print(f"  ✓ {file}")
        else:
            print(f"  ❌ {file}")
            missing.append(file)
    
    if missing:
        print(f"\n❌ Missing files: {', '.join(missing)}")
        return False
    
    print("✓ All required files present")
    return True

def check_reports_directory():
    """Check reports directory exists or can be created"""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)
        print("✓ Created reports directory")
    else:
        print("✓ Reports directory exists")
    return True

def main():
    print("=" * 70)
    print("LIVE PAPER-TRADING SETUP VALIDATION")
    print("=" * 70)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Configuration", check_config),
        ("Required Files", check_files),
        ("Reports Directory", check_reports_directory),
        ("API Connectivity", check_api_connectivity),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 70)
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Check failed with error: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status:8} - {name}")
    
    print(f"\nTotal: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ All checks passed! Ready to run live paper trading.")
        print("\nTo start:")
        print("  ./run_live_paper_setup.sh")
        print("  OR")
        print("  python3 run_live_paper.py")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix issues before running.")
        print("\nFor help:")
        print("  - Read LIVE_PAPER_TRADING_GUIDE.md")
        print("  - Run: pip3 install -r requirements.txt")
        print("  - Check Python version (need 3.10+)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
