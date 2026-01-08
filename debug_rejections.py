import sys
sys.path.insert(0, 'src')
from predarb.config import load_config
from predarb.stress_scenarios import HappyPathScenario
from predarb.engine import Engine
from predarb.broker import PaperBroker
from predarb.risk import RiskManager

config = load_config("config.yml")
scenario = HappyPathScenario()

# Get markets
markets = scenario.fetch_markets()
market_lookup = {m.id: m for m in markets}

# Create broker and risk manager
broker = PaperBroker(config.broker)
risk = RiskManager(config.risk, broker)

# Create engine and get opportunities
engine = Engine(config, scenario)
opps = engine.run_once()

print("=" * 70)
print("REJECTION ANALYSIS")
print("=" * 70)
print(f"\nTotal opportunities detected: {len(opps)}")
print(f"\nConfig settings:")
print(f"  min_liquidity_usd: {config.risk.min_liquidity_usd}")
print(f"  min_net_edge_threshold: {config.risk.min_net_edge_threshold}")
print(f"  max_open_positions: {config.risk.max_open_positions}")
print(f"  max_allocation_per_market: {config.risk.max_allocation_per_market}")

# Test each opportunity
approved = 0
rejections = {
    'edge_too_low': 0,
    'liquidity_too_low': 0,
    'max_positions': 0,
    'allocation_exceeded': 0,
    'approved': 0
}

for i, opp in enumerate(opps):
    # Check edge
    if opp.net_edge < config.risk.min_net_edge_threshold:
        rejections['edge_too_low'] += 1
        if i < 3:
            print(f"\n❌ Opp {i+1}: Edge too low ({opp.net_edge:.4f} < {config.risk.min_net_edge_threshold})")
        continue
    
    # Check liquidity
    has_low_liq = False
    for mid in opp.market_ids:
        market = market_lookup.get(mid)
        if market and market.liquidity < config.risk.min_liquidity_usd:
            has_low_liq = True
            if i < 3:
                print(f"\n❌ Opp {i+1}: Liquidity too low ({market.liquidity} < {config.risk.min_liquidity_usd})")
            break
    if has_low_liq:
        rejections['liquidity_too_low'] += 1
        continue
    
    # Check positions
    open_pos = sum(1 for qty in broker.positions.values() if qty != 0)
    if open_pos >= config.risk.max_open_positions:
        rejections['max_positions'] += 1
        if i < 3:
            print(f"\n❌ Opp {i+1}: Max positions ({open_pos} >= {config.risk.max_open_positions})")
        continue
    
    # Check allocation
    total_equity = broker.cash
    est_cost = sum(a.limit_price * a.amount for a in opp.actions)
    max_per_market = total_equity * config.risk.max_allocation_per_market
    if est_cost > max_per_market:
        rejections['allocation_exceeded'] += 1
        if i < 3:
            print(f"\n❌ Opp {i+1}: Allocation exceeded (${est_cost:.2f} > ${max_per_market:.2f})")
        continue
    
    # Approved!
    rejections['approved'] += 1
    approved += 1
    if i < 3:
        print(f"\n✅ Opp {i+1}: APPROVED (edge={opp.net_edge:.4f}, cost=${est_cost:.2f})")

print(f"\n{'=' * 70}")
print("REJECTION REASONS:")
print("=" * 70)
for reason, count in rejections.items():
    pct = count/len(opps)*100 if opps else 0
    icon = "✅" if reason == "approved" else "❌"
    print(f"{icon} {reason:25s}: {count:3d} ({pct:5.1f}%)")

print(f"\n{'=' * 70}")
if rejections['approved'] > 0:
    print(f"✅ {rejections['approved']} opportunities would be approved with current settings")
else:
    print("❌ ALL opportunities rejected!")
    print("\nMost common rejection:")
    max_reason = max((k for k in rejections if k != 'approved'), key=lambda k: rejections[k])
    print(f"   → {max_reason}: {rejections[max_reason]} rejections")
