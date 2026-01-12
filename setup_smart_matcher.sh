#!/bin/bash
#
# Quick Setup Script for Smart Semantic Matcher
# Run: bash setup_smart_matcher.sh
#

set -e

echo "================================================"
echo "Smart Semantic Matcher - Quick Setup"
echo "================================================"
echo ""

# 1. Check Python
echo "1. Checking Python version..."
python3 --version || { echo "❌ Python 3 not found"; exit 1; }
echo "✅ Python found"
echo ""

# 2. Install dependencies
echo "2. Installing dependencies..."
pip3 install --quiet sentence-transformers numpy python-dateutil 2>/dev/null || {
    echo "⚠️  Dependency installation may require sudo or virtual environment"
    echo "Run manually: pip3 install sentence-transformers numpy python-dateutil"
}
echo "✅ Dependencies installed"
echo ""

# 3. Pre-download model (optional but recommended)
echo "3. Pre-downloading SBERT model (80MB, one-time)..."
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2', cache_folder='./.sentence_transformers_cache')" 2>&1 | grep -v "WARNING" || true
echo "✅ Model downloaded"
echo ""

# 4. Run test
echo "4. Running test suite..."
if python3 test_smart_matcher.py 2>&1 | tail -5; then
    echo "✅ Tests passed"
else
    echo "⚠️  Tests failed - check dependencies"
fi
echo ""

# 5. Check for market data
echo "5. Checking for market data..."
if [ -f "kalshi_markets.json" ] && [ -f "polymarket_markets.json" ]; then
    echo "✅ Market data found"
    echo ""
    echo "6. Running smart matcher..."
    python3 smart_matcher.py
    echo ""
    echo "✅ Matcher completed! Check smart_pairs.json"
else
    echo "⚠️  Market data not found"
    echo ""
    echo "To download data, run:"
    echo "  python3 scripts/download_markets.py --kalshi --poly --max-markets 500"
    echo ""
    echo "Or use existing dumps:"
    echo "  cd market_dumps/LATEST/ && cp *.json ../../ && cd ../.."
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  • Read: SMART_MATCHER_README.md"
echo "  • View output: cat smart_pairs.json | jq '.[0]'"
echo "  • Configure: Edit smart_matcher.py (lines 135-140)"
echo ""
