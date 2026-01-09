#!/bin/bash
# Quick start guide for dual-venue stress testing

set -e

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║    DUAL-VENUE STRESS TESTING - QUICK START GUIDE                    ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Check Python environment
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found at .venv/"
    echo "   Please create it first: python3 -m venv .venv"
    exit 1
fi

echo "✓ Virtual environment found"
echo ""

# Set PYTHONPATH
export PYTHONPATH=/opt/prediction-market-arbitrage/src
echo "✓ PYTHONPATH set to: $PYTHONPATH"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OPTION 1: Run Comprehensive Test Suite (RECOMMENDED)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This runs ALL validations and tests every arbitrage type:"
echo ""
echo "  .venv/bin/python run_all_scenarios.py"
echo ""
read -p "Press ENTER to run, or Ctrl+C to skip..."
echo ""

.venv/bin/python run_all_scenarios.py

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OPTION 2: Run CLI Dual-Stress Command"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This uses the CLI interface to run cross-venue scenarios:"
echo ""
echo "  .venv/bin/python -m predarb dual-stress --cross-venue --seed 42"
echo ""
read -p "Press ENTER to run, or Ctrl+C to skip..."
echo ""

.venv/bin/python -m predarb dual-stress --cross-venue --seed 42

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OPTION 3: Run Unit Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This runs 38 unit tests for the injection layer:"
echo ""
echo "  .venv/bin/python -m pytest tests/test_dual_injection.py tests/test_cross_venue_scenarios.py -v"
echo ""
read -p "Press ENTER to run, or Ctrl+C to skip..."
echo ""

.venv/bin/python -m pytest tests/test_dual_injection.py tests/test_cross_venue_scenarios.py -v

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                     ✅ ALL TESTS COMPLETED                           ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Results available in:"
echo "   - reports/unified_report.json"
echo "   - reports/paper_trades.csv"
echo "   - reports/live_summary.csv"
echo ""
echo "📚 Documentation:"
echo "   - DUAL_VENUE_STRESS_TESTING.md (user guide)"
echo "   - IMPLEMENTATION_DUAL_VENUE_STRESS_TESTING.md (implementation summary)"
echo ""
echo "🎯 Next steps:"
echo "   - Customize scenarios in src/predarb/cross_venue_scenarios.py"
echo "   - Create custom fixtures in JSON format"
echo "   - Integrate into CI/CD pipeline"
echo ""
