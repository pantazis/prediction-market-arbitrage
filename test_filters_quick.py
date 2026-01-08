import sys
sys.path.insert(0, 'src')
from predarb.config import load_config
from predarb.stress_scenarios import HappyPathScenario
from predarb.engine import Engine

config = load_config("config.yml")
scenario = HappyPathScenario()
engine = Engine(config, scenario)

print("🧪 Testing new filters with HappyPathScenario...")
print(f"   min_liquidity_usd: {config.risk.min_liquidity_usd} (was 500)")
print(f"   min_volume_24h: {config.filter.min_volume_24h} (was 1000 🔴)")
print(f"   min_liquidity: {config.filter.min_liquidity} (was 10000)")

opps = engine.run_once()
print(f"\n📊 Results: {len(opps)} opportunities detected")

# Check the unified report
import json
with open('reports/unified_report.json') as f:
    report = json.load(f)
    last = report['iterations'][-1]
    print(f"   Detected: {last['detected']}")
    print(f"   Approved: {last['approved']}")
    if last['detected'] > 0:
        rate = last['approved']/last['detected']*100
        print(f"   Approval rate: {rate:.1f}%")
        if rate > 50:
            print(f"\n✅ SUCCESS! {rate:.0f}% approval (was 4.3%)")
        elif rate > 20:
            print(f"\n✅ IMPROVED! {rate:.0f}% approval (was 4.3%)")
        else:
            print(f"\n⚠️  Still low: {rate:.0f}% approval")
