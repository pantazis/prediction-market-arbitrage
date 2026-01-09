#!/bin/bash
# ========================================================================
# Live Paper-Trading Setup & Execution Script
# ========================================================================
# This script sets up and runs the live paper-trading arbitrage bot
# with real-time market data only (no historical/injected data).
# ========================================================================

set -e  # Exit on any error

echo "========================================================================"
echo "LIVE PAPER-TRADING ARBITRAGE BOT - SETUP & RUN"
echo "========================================================================"
echo ""

# ============================================================================
# STEP 1: Environment Check
# ============================================================================
echo "Step 1: Checking environment..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Please install Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Python version: $PYTHON_VERSION"

# Check if we're in the correct directory
if [ ! -f "run_live_paper.py" ]; then
    echo "❌ run_live_paper.py not found. Please run from project root."
    exit 1
fi
echo "✓ Project directory confirmed"

# ============================================================================
# STEP 2: Install Dependencies
# ============================================================================
echo ""
echo "Step 2: Installing dependencies..."

if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found"
    exit 1
fi

python3 -m pip install -r requirements.txt --quiet
echo "✓ Dependencies installed"

# ============================================================================
# STEP 3: Verify Configuration
# ============================================================================
echo ""
echo "Step 3: Verifying configuration..."

if [ ! -f "config_live_paper.yml" ]; then
    echo "❌ config_live_paper.yml not found"
    exit 1
fi

# Test config loading
python3 -c "
from predarb.config import load_config
config = load_config('config_live_paper.yml')
print(f'✓ Config loaded successfully')
print(f'  - Initial capital: \${config.broker.initial_cash:.2f} USDC')
print(f'  - Refresh rate: {config.engine.refresh_seconds}s')
print(f'  - Stop loss: {config.risk.kill_switch_drawdown:.1%}')
print(f'  - Max per trade: {config.risk.max_allocation_per_market:.1%}')
"

# ============================================================================
# STEP 4: Test API Connectivity
# ============================================================================
echo ""
echo "Step 4: Testing API connectivity..."

python3 -c "
import sys
sys.path.insert(0, 'src')
from predarb.config import load_config
from predarb.polymarket_client import PolymarketClient

config = load_config('config_live_paper.yml')
client = PolymarketClient(config.polymarket)
try:
    markets = client.fetch_markets()
    print(f'✓ Successfully fetched {len(markets)} markets from Polymarket')
    if markets:
        print(f'  - Sample: {markets[0].question[:60]}...')
except Exception as e:
    print(f'⚠ Warning: Could not fetch markets: {e}')
    print('  The bot will retry during execution')
"

# ============================================================================
# STEP 5: Create Reports Directory
# ============================================================================
echo ""
echo "Step 5: Setting up reports directory..."

mkdir -p reports
echo "✓ Reports directory ready"

# ============================================================================
# STEP 6: Parse Command Line Arguments
# ============================================================================
echo ""
echo "Step 6: Configuring run parameters..."

# Default values
DURATION=8.0
CAPITAL=500.0
LOG_LEVEL="INFO"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --capital)
            CAPITAL="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --help)
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --duration HOURS    Run duration in hours (default: 8.0)"
            echo "  --capital USDC      Starting capital in USDC (default: 500.0)"
            echo "  --log-level LEVEL   Log level: DEBUG|INFO|WARNING|ERROR (default: INFO)"
            echo "  --help              Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                              # 8 hours, 500 USDC"
            echo "  $0 --duration 0.5               # 30 minutes"
            echo "  $0 --capital 1000 --duration 4  # 1000 USDC for 4 hours"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "Configuration:"
echo "  - Duration: ${DURATION} hours"
echo "  - Starting Capital: \$${CAPITAL} USDC"
echo "  - Log Level: ${LOG_LEVEL}"

# ============================================================================
# STEP 7: Final Confirmation
# ============================================================================
echo ""
echo "========================================================================"
echo "READY TO START LIVE PAPER TRADING"
echo "========================================================================"
echo ""
echo "⚠️  IMPORTANT REMINDERS:"
echo "  • This is PAPER TRADING only (no real orders)"
echo "  • Uses ONLY real-time market data (no historical/fake data)"
echo "  • Bot will stop automatically after ${DURATION} hours"
echo "  • Stop loss triggers at 15% drawdown"
echo "  • Press Ctrl+C to stop manually"
echo ""
echo "Output:"
echo "  • Live console: Real-time progress updates"
echo "  • Trade log: reports/live_paper_trades.csv"
echo "  • Unified report: reports/unified_report.json"
echo "  • Summary: reports/live_summary.csv"
echo ""
echo "========================================================================"
echo ""

# Ask for confirmation (skip if --yes flag provided)
if [[ ! "$*" =~ "--yes" ]]; then
    read -p "Start live paper trading? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted by user"
        exit 0
    fi
fi

# ============================================================================
# STEP 8: Run Live Paper Trading
# ============================================================================
echo ""
echo "========================================================================"
echo "STARTING LIVE PAPER TRADING SESSION"
echo "========================================================================"
echo ""

# Record start time
START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "Start Time: $START_TIME"
echo ""

# Run the bot
python3 run_live_paper.py \
    --duration "$DURATION" \
    --capital "$CAPITAL" \
    --log-level "$LOG_LEVEL"

EXIT_CODE=$?

# ============================================================================
# STEP 9: Post-Run Summary
# ============================================================================
echo ""
echo "========================================================================"
echo "SESSION COMPLETE"
echo "========================================================================"

END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "End Time: $END_TIME"
echo "Exit Code: $EXIT_CODE"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Session completed successfully"
else
    echo "⚠ Session ended with errors (code: $EXIT_CODE)"
fi

echo ""
echo "Reports available at:"
echo "  - reports/live_paper_trades.csv"
echo "  - reports/unified_report.json"
echo "  - reports/live_summary.csv"
echo ""

# Check if reports exist
if [ -f "reports/live_paper_trades.csv" ]; then
    TRADE_COUNT=$(wc -l < reports/live_paper_trades.csv)
    echo "✓ Trade log contains $TRADE_COUNT lines"
fi

if [ -f "reports/unified_report.json" ]; then
    echo "✓ Unified report generated"
fi

echo ""
echo "To view results:"
echo "  cat reports/live_paper_trades.csv"
echo "  python3 -m json.tool reports/unified_report.json | less"
echo ""
echo "========================================================================"

exit $EXIT_CODE
