#!/bin/bash
# ========================================================================
# Multi-Day Dry Run Monitoring Script
# ========================================================================
# Monitor the 72-hour paper trading dry run with real-time updates
# ========================================================================

echo "========================================================================"
echo "MULTI-DAY DRY RUN MONITORING DASHBOARD"
echo "========================================================================"
echo ""

# Check if bot is running
echo "📊 BOT STATUS:"
echo "------------------------------------------------------------------------"
BOT_PID=$(pgrep -f "run_live_paper.py" || echo "")
if [ -n "$BOT_PID" ]; then
    echo "✓ Bot is RUNNING (PID: $BOT_PID)"
    ps -p $BOT_PID -o pid,ppid,cmd,etime,pcpu,pmem --no-headers | awk '{print "  Process: " $1 " | Uptime: " $4 " | CPU: " $5 "% | Mem: " $6 "%"}'
else
    echo "✗ Bot is NOT RUNNING"
fi
echo ""

# Show runtime parameters
echo "🎯 CONFIGURATION:"
echo "------------------------------------------------------------------------"
echo "  Duration Target:    72 hours (3 days)"
echo "  Starting Capital:   $1,000 USDC"
echo "  Refresh Interval:   5 seconds"
echo "  Total Iterations:   51,840 (72h × 3600s / 5s)"
echo "  Config File:        config_live_paper.yml"
echo "  Log File:           bot_multiday_dryrun.log"
echo ""

# Check log file
echo "📝 LOG FILE STATUS:"
echo "------------------------------------------------------------------------"
if [ -f "bot_multiday_dryrun.log" ]; then
    LOG_SIZE=$(du -h bot_multiday_dryrun.log | cut -f1)
    LOG_LINES=$(wc -l < bot_multiday_dryrun.log)
    echo "✓ Log file exists"
    echo "  Size: $LOG_SIZE | Lines: $LOG_LINES"
    echo ""
    echo "  Latest entries:"
    tail -5 bot_multiday_dryrun.log | sed 's/^/    /'
else
    echo "✗ Log file not found"
fi
echo ""

# Check reports
echo "📊 GENERATED REPORTS:"
echo "------------------------------------------------------------------------"
if [ -f "reports/live_summary.csv" ]; then
    echo "✓ Live Summary Report:"
    head -2 reports/live_summary.csv | sed 's/^/    /'
fi

if [ -f "reports/paper_trades.csv" ]; then
    TRADE_COUNT=$(wc -l < reports/paper_trades.csv)
    echo "✓ Paper Trades Log: $TRADE_COUNT entries"
fi

if [ -f "reports/unified_report.json" ]; then
    echo "✓ Unified Report: Available"
fi
echo ""

# Show PnL if available
echo "💰 PERFORMANCE SNAPSHOT:"
echo "------------------------------------------------------------------------"
if [ -f "reports/unified_report.json" ]; then
    python3 -c "
import json
try:
    with open('reports/unified_report.json', 'r') as f:
        data = json.load(f)
    if 'session_summary' in data:
        print(f\"  Opportunities Detected: {data.get('total_opportunities_detected', 0)}\")
        print(f\"  Opportunities Approved: {data.get('total_opportunities_approved', 0)}\")
        print(f\"  Total Trades: {data.get('total_trades_executed', 0)}\")
except Exception as e:
    print(f'  Unable to parse report: {e}')
" 2>/dev/null || echo "  Report not yet available"
else
    echo "  Report not yet generated"
fi
echo ""

# Show recent market activity
echo "🔍 RECENT ACTIVITY:"
echo "------------------------------------------------------------------------"
if [ -f "bot_multiday_dryrun.log" ]; then
    echo "  Last 3 opportunity detections:"
    grep -i "detected.*opportunities" bot_multiday_dryrun.log | tail -3 | sed 's/^/    /'
else
    echo "  No activity log available yet"
fi
echo ""

echo "========================================================================"
echo "COMMANDS:"
echo "------------------------------------------------------------------------"
echo "  Monitor live:       tail -f bot_multiday_dryrun.log"
echo "  Stop bot:           pkill -f run_live_paper.py"
echo "  View reports:       ls -lh reports/"
echo "  This dashboard:     bash monitor_multiday_dryrun.sh"
echo "========================================================================"
