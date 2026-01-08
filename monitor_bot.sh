#!/bin/bash
# Monitor continuous bot status
# Usage: ./monitor_bot.sh

cd /opt/prediction-market-arbitrage

echo "=============================================================="
echo "CONTINUOUS BOT MONITOR"
echo "=============================================================="
echo ""

# Check if bot is running
if [ -f bot.pid ]; then
    PID=$(cat bot.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "✓ Bot is RUNNING (PID: $PID)"
        echo "  Started: $(ps -p $PID -o lstart= 2>/dev/null)"
        echo "  CPU: $(ps -p $PID -o %cpu= 2>/dev/null)%"
        echo "  Memory: $(ps -p $PID -o %mem= 2>/dev/null)%"
    else
        echo "✗ Bot is NOT RUNNING (stale PID file)"
    fi
else
    echo "✗ No PID file found"
fi

echo ""
echo "=============================================================="
echo "REPORTS STATUS"
echo "=============================================================="

if [ -f reports/unified_report.json ]; then
    python3 <<EOF
import json
with open('reports/unified_report.json') as f:
    data = json.load(f)
    
print(f"Iterations logged: {len(data['iterations'])}")
print(f"Opportunities executed: {len(data['opportunity_executions'])}")
print(f"Trades executed: {len(data['trades'])}")
print(f"Last updated: {data['metadata']['last_updated']}")

if data['iterations']:
    last = data['iterations'][-1]
    print(f"\nLast iteration #{last['iteration']}:")
    print(f"  Markets: {last['markets_count']}")
    print(f"  Detected: {last['detected_count']}")
    print(f"  Approved: {last['approved_count']}")
    if last['approved_count'] > 0:
        print(f"  Approval rate: {last['approved_count']/last['detected_count']*100:.1f}%")
        
if data['trades']:
    total_pnl = sum(t.get('realized_pnl', 0) for t in data['trades'])
    print(f"\nTotal P&L: \${total_pnl:.2f}")
EOF
else
    echo "No unified report found yet"
fi

echo ""
echo "=============================================================="
echo "LIVE SUMMARY (last 5 rows)"
echo "=============================================================="
if [ -f reports/live_summary.csv ]; then
    tail -5 reports/live_summary.csv | column -t -s,
else
    echo "No live summary found yet"
fi

echo ""
echo "=============================================================="
echo "To view live log: tail -f bot_continuous.log"
echo "To stop bot: kill \$(cat bot.pid)"
echo "=============================================================="
