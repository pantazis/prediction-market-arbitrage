#!/bin/bash
# ========================================================================
# LIVE PAPER-TRADING INSTALLATION & RUN SCRIPT
# ========================================================================
# Run this script to install dependencies and start live paper trading
# ========================================================================

set -e

echo "========================================================================="
echo "LIVE PAPER-TRADING ARBITRAGE BOT - INSTALLATION & EXECUTION"
echo "========================================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "run_live_paper.py" ]; then
    echo "❌ Error: Must run from /opt/prediction-market-arbitrage directory"
    exit 1
fi

echo "Step 1: Installing dependencies..."
echo "Note: This will install Python packages system-wide"
echo ""

# Install dependencies
pip3 install -r requirements.txt --break-system-packages -q

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    echo "   Try manually: pip3 install -r requirements.txt --break-system-packages"
    exit 1
fi

echo ""
echo "Step 2: Validating setup..."
python3 validate_live_paper_setup.py

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All checks passed! Ready to run."
    echo ""
    echo "========================================================================="
    echo "CHOOSE YOUR OPTION:"
    echo "========================================================================="
    echo ""
    echo "1. Quick test (6 minutes):"
    echo "   python3 run_live_paper.py --duration 0.1"
    echo ""
    echo "2. Default run (8 hours, 500 USDC):"
    echo "   python3 run_live_paper.py"
    echo ""
    echo "3. Custom run:"
    echo "   python3 run_live_paper.py --duration 4 --capital 1000"
    echo ""
    echo "========================================================================="
    echo ""
    read -p "Run quick test now? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "Starting 6-minute test run..."
        echo ""
        python3 run_live_paper.py --duration 0.1
    else
        echo "Setup complete. Run manually when ready."
    fi
else
    echo ""
    echo "⚠️  Some validation checks failed."
    echo "   Review the output above and fix any issues."
    echo "   You can still try to run: python3 run_live_paper.py --help"
fi
