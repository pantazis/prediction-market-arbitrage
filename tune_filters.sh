#!/bin/bash
# Quick filter adjustment and testing script

echo "╔════════════════════════════════════════════════════════════╗"
echo "║          FILTER ADJUSTMENT & TESTING TOOL                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if bot is running
if [ -f bot.pid ] && ps -p $(cat bot.pid) > /dev/null 2>&1; then
    echo "⚠️  WARNING: Bot is currently running (PID: $(cat bot.pid))"
    echo ""
    read -p "Stop bot and continue? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Stopping bot..."
        kill $(cat bot.pid)
        sleep 2
    else
        echo "Exiting. Stop bot manually with: kill \$(cat bot.pid)"
        exit 1
    fi
fi

echo "Select filter preset:"
echo ""
echo "1) RELAXED - For testing, catch more opportunities"
echo "   min_liquidity_usd: 250"
echo "   min_net_edge_threshold: 0.002"
echo "   min_volume_24h: 500"
echo "   min_liquidity: 5000"
echo "   min_days_to_expiry: 1"
echo ""
echo "2) CURRENT - Your existing settings"
echo "   min_liquidity_usd: 500"
echo "   min_net_edge_threshold: 0.005"
echo "   min_volume_24h: 1000"
echo "   min_liquidity: 10000"
echo "   min_days_to_expiry: 3"
echo ""
echo "3) STRICT - Ultra conservative, high quality only"
echo "   min_liquidity_usd: 1000"
echo "   min_net_edge_threshold: 0.01"
echo "   min_volume_24h: 5000"
echo "   min_liquidity: 20000"
echo "   min_days_to_expiry: 7"
echo ""
echo "4) CUSTOM - Edit config.yml manually"
echo ""

read -p "Choice (1-4): " choice

# Backup current config
cp config.yml config.yml.backup
echo "✓ Backed up current config to config.yml.backup"

case $choice in
    1)
        echo "Applying RELAXED filters..."
        cat > config_temp.yml <<EOF
polymarket:
  host: "https://clob.polymarket.com"
risk:
  max_allocation_per_market: 0.05
  max_open_positions: 20
  min_liquidity_usd: 250.0
  min_net_edge_threshold: 0.002
  kill_switch_drawdown: 0.2
broker:
  initial_cash: 10000.0
  fee_bps: 10.0
  slippage_bps: 20.0
  depth_fraction: 0.05
engine:
  refresh_seconds: 1.0
  iterations: 10
  report_path: "reports/paper_trades.csv"
filter:
  max_spread_pct: 0.1
  min_volume_24h: 500
  min_liquidity: 5000
  min_days_to_expiry: 1
  min_liquidity_multiple: 20
  target_order_size_usd: 500
  require_resolution_source: true
  allow_missing_end_time: false
  min_rank_score: 20
detectors:
  parity_threshold: 0.99
  duplicate_price_diff_threshold: 0.05
  exclusive_sum_tolerance: 0.03
  ladder_tolerance: 0.0
  timelag_price_jump: 0.05
  timelag_persistence_minutes: 5
telegram:
  enabled: true
  bot_token: ""
  chat_id: ""
EOF
        mv config_temp.yml config.yml
        ;;
    2)
        echo "Keeping CURRENT filters (restored from backup)"
        cp config.yml.backup config.yml
        ;;
    3)
        echo "Applying STRICT filters..."
        cat > config_temp.yml <<EOF
polymarket:
  host: "https://clob.polymarket.com"
risk:
  max_allocation_per_market: 0.05
  max_open_positions: 20
  min_liquidity_usd: 1000.0
  min_net_edge_threshold: 0.01
  kill_switch_drawdown: 0.2
broker:
  initial_cash: 10000.0
  fee_bps: 10.0
  slippage_bps: 20.0
  depth_fraction: 0.05
engine:
  refresh_seconds: 1.0
  iterations: 10
  report_path: "reports/paper_trades.csv"
filter:
  max_spread_pct: 0.1
  min_volume_24h: 5000
  min_liquidity: 20000
  min_days_to_expiry: 7
  min_liquidity_multiple: 20
  target_order_size_usd: 500
  require_resolution_source: true
  allow_missing_end_time: false
  min_rank_score: 20
detectors:
  parity_threshold: 0.99
  duplicate_price_diff_threshold: 0.05
  exclusive_sum_tolerance: 0.03
  ladder_tolerance: 0.0
  timelag_price_jump: 0.05
  timelag_persistence_minutes: 5
telegram:
  enabled: true
  bot_token: ""
  chat_id: ""
EOF
        mv config_temp.yml config.yml
        ;;
    4)
        echo "Opening config.yml in editor..."
        ${EDITOR:-nano} config.yml
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "✓ Config updated!"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "NEXT STEPS"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "1) Quick test (30 seconds):"
echo "   python -m predarb stress --scenario happy_path --no-verify"
echo ""
echo "2) Analyze results:"
echo "   python analyze_filter_effectiveness.py"
echo ""
echo "3) If satisfied, start continuous run:"
echo "   python run_continuous_mixed.py --scenario high_volume --days 2"
echo ""
echo "4) Restore previous config if needed:"
echo "   mv config.yml.backup config.yml"
echo ""
