#!/usr/bin/env python3
"""
Analyze filter effectiveness against injected stress test data.

This script helps you understand:
1. Are filters catching/rejecting injected opportunities?
2. What's the approval rate for real vs injected markets?
3. Which filters are most active (rejecting most)?
4. How to tune filters to better catch edge cases
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.config import load_config
from predarb.injection import InjectionSource
from predarb.polymarket_client import PolymarketClient
from predarb.detectors import *
from predarb.risk import RiskManager


def analyze_current_run():
    """Analyze the current continuous run."""
    print("="*70)
    print("CURRENT RUN ANALYSIS")
    print("="*70)
    
    try:
        with open('reports/unified_report.json', 'r') as f:
            data = json.load(f)
        
        print(f"\nTotal iterations: {len(data['iterations'])}")
        
        # Aggregate stats
        total_markets = 0
        total_detected = 0
        total_approved = 0
        
        for it in data['iterations']:
            markets = it['markets']['count']
            detected = it['opportunities_detected']['count']
            approved = it['opportunities_approved']['count']
            
            total_markets += markets
            total_detected += detected
            total_approved += approved
        
        avg_markets = total_markets / len(data['iterations']) if data['iterations'] else 0
        
        print(f"Average markets per iteration: {avg_markets:.0f}")
        print(f"Total opportunities detected: {total_detected}")
        print(f"Total opportunities approved: {total_approved}")
        
        if total_detected > 0:
            approval_rate = (total_approved / total_detected) * 100
            rejection_rate = 100 - approval_rate
            print(f"Overall approval rate: {approval_rate:.1f}%")
            print(f"Overall rejection rate: {rejection_rate:.1f}%")
            
            print(f"\n⚠️  {rejection_rate:.0f}% of detected opportunities are being REJECTED by filters/risk")
        
        # Analyze executions by market type
        print(f"\n{'='*70}")
        print("EXECUTION ANALYSIS (Injected vs Real)")
        print("="*70)
        
        injected_opps = []
        real_opps = []
        
        for ex in data.get('opportunity_executions', []):
            if 'opportunity' in ex and 'market_ids' in ex['opportunity']:
                market_ids = ex['opportunity']['market_ids']
                if any('INJECTED' in str(mid) for mid in market_ids):
                    injected_opps.append(ex)
                else:
                    real_opps.append(ex)
        
        print(f"\nOpportunities from INJECTED markets: {len(injected_opps)}")
        print(f"Opportunities from REAL markets: {len(real_opps)}")
        
        if injected_opps:
            print(f"\nInjected opportunities by status:")
            by_status = {}
            for ex in injected_opps:
                status = ex.get('status', 'unknown')
                by_status[status] = by_status.get(status, 0) + 1
            for status, count in sorted(by_status.items()):
                print(f"  {status}: {count}")
        
        if real_opps:
            print(f"\nReal opportunities by status:")
            by_status = {}
            for ex in real_opps:
                status = ex.get('status', 'unknown')
                by_status[status] = by_status.get(status, 0) + 1
            for status, count in sorted(by_status.items()):
                print(f"  {status}: {count}")
        
        # Check if injected opportunities are being approved
        if total_approved == 0 and len(injected_opps) > 0:
            print(f"\n⚠️  WARNING: Detected {total_detected} opportunities but NONE approved!")
            print("   This suggests filters/risk manager are too strict.")
        
    except FileNotFoundError:
        print("No report file found yet. Run the bot first.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def test_filters_on_scenarios():
    """Test what filters do to each stress scenario."""
    print("\n" + "="*70)
    print("FILTER TESTING ON STRESS SCENARIOS")
    print("="*70)
    
    config = load_config("config.yml")
    
    scenarios = [
        "high_volume",
        "happy_path", 
        "many_risk_rejections",
        "partial_fill",
    ]
    
    for scenario_name in scenarios:
        print(f"\n{'='*70}")
        print(f"Scenario: {scenario_name}")
        print("="*70)
        
        try:
            # Create scenario
            provider = InjectionSource.from_spec(f"scenario:{scenario_name}", seed=42)
            markets = provider.fetch_markets()
            
            print(f"\nGenerated {len(markets)} markets")
            
            # Apply detectors
            from predarb.detectors.parity import ParityDetector
            from predarb.detectors.duplicates import DuplicatesDetector
            
            detector = ParityDetector(config.detectors)
            opportunities = []
            
            for market in markets:
                opps = detector.detect([market])
                opportunities.extend(opps)
            
            print(f"Parity detector found: {len(opportunities)} opportunities")
            
            # Apply risk manager
            risk_mgr = RiskManager(config.risk, config.broker)
            approved = []
            rejected = []
            
            for opp in opportunities:
                if risk_mgr.approve_opportunity(opp, markets):
                    approved.append(opp)
                else:
                    rejected.append(opp)
            
            print(f"Risk manager approved: {len(approved)}")
            print(f"Risk manager rejected: {len(rejected)}")
            
            if len(rejected) > 0 and len(opportunities) > 0:
                rejection_rate = (len(rejected) / len(opportunities)) * 100
                print(f"Rejection rate: {rejection_rate:.1f}%")
                
                # Sample rejection reasons (would need to instrument RiskManager to get actual reasons)
                print(f"\nLikely rejection reasons:")
                print(f"  - Low liquidity (min_liquidity_usd: {config.risk.min_liquidity_usd})")
                print(f"  - Low edge (min_net_edge_threshold: {config.risk.min_net_edge_threshold})")
            
        except Exception as e:
            print(f"Error testing scenario: {e}")


def suggest_improvements():
    """Suggest filter improvements based on analysis."""
    print("\n" + "="*70)
    print("SUGGESTIONS TO IMPROVE FILTER EFFECTIVENESS")
    print("="*70)
    
    config = load_config("config.yml")
    
    print(f"\nCurrent Risk Settings:")
    print(f"  min_liquidity_usd: {config.risk.min_liquidity_usd}")
    print(f"  min_net_edge_threshold: {config.risk.min_net_edge_threshold}")
    print(f"  max_allocation_per_market: {config.risk.max_allocation_per_market}")
    
    print(f"\nCurrent Filter Settings:")
    print(f"  max_spread_pct: {config.filter.max_spread_pct}")
    print(f"  min_volume_24h: {config.filter.min_volume_24h}")
    print(f"  min_liquidity: {config.filter.min_liquidity}")
    print(f"  min_days_to_expiry: {config.filter.min_days_to_expiry}")
    
    print(f"\n{'='*70}")
    print("RECOMMENDATIONS:")
    print("="*70)
    
    # Read current stats
    try:
        with open('reports/unified_report.json', 'r') as f:
            data = json.load(f)
        
        total_detected = sum(it['opportunities_detected']['count'] for it in data['iterations'])
        total_approved = sum(it['opportunities_approved']['count'] for it in data['iterations'])
        
        if total_detected > 0:
            approval_rate = (total_approved / total_detected) * 100
            
            if approval_rate < 5:
                print(f"\n⚠️  VERY LOW approval rate ({approval_rate:.1f}%)")
                print(f"\nTo capture more opportunities, try RELAXING filters:")
                print(f"  1. Reduce min_liquidity_usd: {config.risk.min_liquidity_usd} → 250")
                print(f"  2. Reduce min_net_edge_threshold: {config.risk.min_net_edge_threshold} → 0.002")
                print(f"  3. Reduce min_volume_24h: {config.filter.min_volume_24h} → 500")
                print(f"  4. Reduce min_liquidity: {config.filter.min_liquidity} → 5000")
                
            elif approval_rate > 50:
                print(f"\n⚠️  HIGH approval rate ({approval_rate:.1f}%)")
                print(f"\nTo be more selective, try TIGHTENING filters:")
                print(f"  1. Increase min_liquidity_usd: {config.risk.min_liquidity_usd} → 1000")
                print(f"  2. Increase min_net_edge_threshold: {config.risk.min_net_edge_threshold} → 0.01")
                
            else:
                print(f"\n✓ Approval rate ({approval_rate:.1f}%) looks reasonable")
                print(f"  Filters seem well-calibrated for current market conditions")
    
    except Exception:
        pass
    
    print(f"\n{'='*70}")
    print("TO TEST DIFFERENT FILTER SETTINGS:")
    print("="*70)
    print("""
1. Edit config.yml with new filter values
2. Run a quick stress test:
   python -m predarb stress --scenario happy_path --no-verify
3. Check reports/unified_report.json for approval rates
4. Iterate until you find good balance

Example relaxed filters (more opportunities):
  risk:
    min_liquidity_usd: 250
    min_net_edge_threshold: 0.002
  filter:
    min_volume_24h: 500
    min_liquidity: 5000
    min_days_to_expiry: 1

Example strict filters (higher quality):
  risk:
    min_liquidity_usd: 1000
    min_net_edge_threshold: 0.01
  filter:
    min_volume_24h: 5000
    min_liquidity: 20000
    min_days_to_expiry: 7
    """)


def main():
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " FILTER EFFECTIVENESS ANALYZER ".center(68) + "║")
    print("╚" + "="*68 + "╝")
    
    # Analyze current run
    analyze_current_run()
    
    # Test filters on scenarios
    test_filters_on_scenarios()
    
    # Suggest improvements
    suggest_improvements()
    
    print("\n" + "="*70)
    print("Analysis complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
