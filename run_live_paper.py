#!/usr/bin/env python3
"""
Live Paper-Trading Arbitrage Runner

GOAL:
Run the arbitrage bot using ONLY real-time market data with paper trading.
No historical data, no injected data, no real orders.

FEATURES:
- Real-time API data from Polymarket/Kalshi
- Paper wallet: 500 USDC starting balance
- Full PnL tracking with realized/unrealized breakdown
- Position tracking per venue
- Rebalancing simulation
- Comprehensive reporting
- Automatic stop conditions (duration, loss limits)

USAGE:
    python run_live_paper.py --duration 8           # 8 hours (default)
    python run_live_paper.py --duration 0.5         # 30 minutes
    python run_live_paper.py --capital 1000         # 1000 USDC starting
    python run_live_paper.py --help
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from predarb.config import load_config
from predarb.engine import Engine
from predarb.models import Market

logger = logging.getLogger(__name__)


class LivePaperTradingRunner:
    """
    Manages live paper trading session with real-time data only.
    
    Implements:
    - Paper wallet tracking
    - Real-time market data fetching
    - Position management
    - PnL calculation
    - Stop conditions
    - Comprehensive reporting
    """
    
    def __init__(self, config_path: str, duration_hours: float, initial_capital: float):
        """
        Initialize live paper trading runner.
        
        Args:
            config_path: Path to config file
            duration_hours: How long to run (hours)
            initial_capital: Starting USDC balance
        """
        self.config = load_config(config_path)
        self.duration_hours = duration_hours
        self.initial_capital = initial_capital
        
        # Override config with runtime parameters
        self.config.broker.initial_cash = initial_capital
        
        # Calculate iterations from duration and refresh rate
        refresh_seconds = self.config.engine.refresh_seconds
        total_seconds = duration_hours * 3600
        self.config.engine.iterations = int(total_seconds / refresh_seconds)
        
        # Initialize engine
        self.engine = Engine(self.config)
        
        # Track session metrics
        self.start_time = None
        self.end_time = None
        self.total_opportunities_found = 0
        self.total_opportunities_approved = 0
        self.total_opportunities_rejected = 0
        self.rejection_reasons: Dict[str, int] = {}
        self.max_drawdown = 0.0
        self.peak_balance = initial_capital
        
    def validate_live_data_only(self):
        """
        Verify that we're using real-time data only (no injection).
        """
        # Check that no clients are injection providers
        for client in self.engine.clients:
            class_name = client.__class__.__name__
            if "Injection" in class_name or "Static" in class_name or "Fake" in class_name:
                raise RuntimeError(
                    f"VALIDATION FAILED: Client {class_name} appears to be using "
                    f"injected/fake data. Live paper trading requires ONLY real-time "
                    f"market data from actual exchanges."
                )
        
        logger.info("✓ Validation passed: Using real-time data only")
        
    def check_stop_conditions(self) -> tuple[bool, str]:
        """
        Check if any stop conditions are met.
        
        Returns:
            (should_stop, reason)
        """
        # Check drawdown limit
        current_balance = self.engine.broker.cash
        drawdown = (self.peak_balance - current_balance) / self.peak_balance
        
        if drawdown > self.config.risk.kill_switch_drawdown:
            return True, f"Drawdown limit hit: {drawdown:.1%} > {self.config.risk.kill_switch_drawdown:.1%}"
        
        # Update peak for tracking
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        # Update max drawdown
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
        
        return False, ""
    
    def print_wallet_state(self, iteration: int):
        """Print current wallet state."""
        broker = self.engine.broker
        
        # Calculate unrealized PnL (requires market data)
        unrealized_pnl = 0.0
        if self.engine._last_markets:
            market_lookup = {m.id: m for m in self.engine._last_markets}
            unrealized_pnl = broker._unrealized_pnl(market_lookup)
        
        total_equity = broker.cash + unrealized_pnl
        realized_pnl = broker.cash - self.initial_capital
        
        print(f"\n{'='*70}")
        print(f"Iteration {iteration}/{self.config.engine.iterations}")
        print(f"{'='*70}")
        print(f"Cash Available:    ${broker.cash:,.2f}")
        print(f"Unrealized PnL:    ${unrealized_pnl:,.2f}")
        print(f"Total Equity:      ${total_equity:,.2f}")
        print(f"Realized PnL:      ${realized_pnl:,.2f}")
        print(f"Active Positions:  {len([v for v in broker.positions.values() if v != 0])}")
        print(f"Total Trades:      {len(broker.trades)}")
        print(f"Max Drawdown:      {self.max_drawdown:.2%}")
        print(f"{'='*70}")
    
    def run(self):
        """
        Execute live paper trading session.
        
        Loop:
        1. Check wallet balances
        2. Fetch real-time prices + order books
        3. Calculate spreads/edges
        4. Validate (fees, slippage, depth, risk limits)
        5. Detect arbitrage opportunities
        6. Paper-execute approved trades
        7. Handle partial fills
        8. Update wallet
        9. Record PnL
        10. Check stop conditions
        11. Log everything
        """
        print("\n" + "="*80)
        print("LIVE PAPER-TRADING ARBITRAGE BOT")
        print("="*80)
        print(f"Configuration:     {Path('config_live_paper.yml').absolute()}")
        print(f"Starting Capital:  ${self.initial_capital:,.2f} USDC")
        print(f"Duration:          {self.duration_hours} hours")
        print(f"Iterations:        {self.config.engine.iterations}")
        print(f"Refresh Rate:      {self.config.engine.refresh_seconds}s")
        print(f"Stop Loss:         {self.config.risk.kill_switch_drawdown:.1%} drawdown")
        print(f"Max Per Trade:     ${self.config.broker.initial_cash * self.config.risk.max_allocation_per_market:,.2f}")
        print(f"Fee:               {self.config.broker.fee_bps} bps")
        print(f"Slippage:          {self.config.broker.slippage_bps} bps")
        print("="*80)
        
        # Validate live data only
        try:
            self.validate_live_data_only()
        except RuntimeError as e:
            print(f"\n❌ {e}")
            sys.exit(1)
        
        # Print enabled detectors
        enabled_detectors = []
        if self.config.detectors.enable_parity:
            enabled_detectors.append("Parity")
        if self.config.detectors.enable_ladder:
            enabled_detectors.append("Ladder")
        if self.config.detectors.enable_exclusive_sum:
            enabled_detectors.append("ExclusiveSum")
        if self.config.detectors.enable_consistency:
            enabled_detectors.append("Consistency")
        if self.config.detectors.enable_duplicate:
            enabled_detectors.append("Duplicate (REQUIRES SHORT SELLING)")
        if self.config.detectors.enable_timelag:
            enabled_detectors.append("TimeLag")
        
        print(f"\nEnabled Detectors: {', '.join(enabled_detectors)}")
        print(f"Report Output:     {self.config.engine.report_path}")
        print("\n" + "="*80)
        print("STARTING TRADING SESSION")
        print("="*80 + "\n")
        
        self.start_time = datetime.now()
        end_target = self.start_time + timedelta(hours=self.duration_hours)
        
        try:
            for i in range(1, self.config.engine.iterations + 1):
                iteration_start = time.time()
                
                # Check if we've hit time limit
                now = datetime.now()
                if now >= end_target:
                    print(f"\n⏰ Duration limit reached: {self.duration_hours} hours")
                    break
                
                # Print wallet state every 10 iterations or on first iteration
                if i == 1 or i % 10 == 0:
                    self.print_wallet_state(i)
                
                # Run one iteration
                logger.info(f"Iteration {i}/{self.config.engine.iterations}")
                
                try:
                    approved_opps = self.engine.run_once()
                    
                    # Track opportunity metrics
                    detected = len(self.engine._last_detected)
                    approved = len(approved_opps)
                    rejected = detected - approved
                    
                    self.total_opportunities_found += detected
                    self.total_opportunities_approved += approved
                    self.total_opportunities_rejected += rejected
                    
                    if detected > 0:
                        print(f"  → Detected: {detected} opportunities, Approved: {approved}, Rejected: {rejected}")
                    
                    # Report iteration to unified reporter
                    self.engine.reporter.report_iteration(
                        iteration=i,
                        all_markets=self.engine._last_markets,
                        detected_opportunities=self.engine._last_detected,
                        approved_opportunities=approved_opps,
                    )
                    
                except Exception as e:
                    logger.error(f"Iteration {i} failed: {e}", exc_info=True)
                    print(f"  ❌ Error: {e}")
                
                # Check stop conditions
                should_stop, reason = self.check_stop_conditions()
                if should_stop:
                    print(f"\n🛑 STOP CONDITION MET: {reason}")
                    break
                
                # Sleep until next iteration
                elapsed = time.time() - iteration_start
                sleep_time = max(0, self.config.engine.refresh_seconds - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
        finally:
            self.end_time = datetime.now()
            self.print_final_report()
    
    def print_final_report(self):
        """Print comprehensive end-of-run report."""
        duration = self.end_time - self.start_time
        broker = self.engine.broker
        
        # Calculate final PnL
        unrealized_pnl = 0.0
        if self.engine._last_markets:
            market_lookup = {m.id: m for m in self.engine._last_markets}
            unrealized_pnl = broker._unrealized_pnl(market_lookup)
        
        final_equity = broker.cash + unrealized_pnl
        total_pnl = final_equity - self.initial_capital
        total_pnl_pct = (total_pnl / self.initial_capital) * 100
        
        # Trade statistics
        trades = broker.trades
        num_buys = len([t for t in trades if t.side == "BUY"])
        num_sells = len([t for t in trades if t.side == "SELL"])
        total_fees = sum(t.fees for t in trades)
        total_slippage = sum(t.slippage for t in trades)
        
        # Win rate calculation (simplified - count profitable closed positions)
        win_count = len([t for t in trades if t.realized_pnl > 0])
        loss_count = len([t for t in trades if t.realized_pnl < 0])
        win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
        
        # Biggest win/loss
        biggest_win = max([t.realized_pnl for t in trades], default=0)
        biggest_loss = min([t.realized_pnl for t in trades], default=0)
        
        # Active positions
        active_positions = {k: v for k, v in broker.positions.items() if v != 0}
        
        print("\n\n" + "="*80)
        print("END-OF-RUN REPORT")
        print("="*80)
        
        print("\n📊 SESSION SUMMARY")
        print("-" * 80)
        print(f"Start Time:        {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End Time:          {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration:          {duration} ({duration.total_seconds()/3600:.2f} hours)")
        print(f"Iterations:        {self.config.engine.iterations} planned")
        
        print("\n💰 WALLET PERFORMANCE")
        print("-" * 80)
        print(f"Initial Capital:   ${self.initial_capital:,.2f} USDC")
        print(f"Final Cash:        ${broker.cash:,.2f} USDC")
        print(f"Unrealized PnL:    ${unrealized_pnl:,.2f} USDC")
        print(f"Final Equity:      ${final_equity:,.2f} USDC")
        print(f"Total PnL:         ${total_pnl:+,.2f} USDC ({total_pnl_pct:+.2f}%)")
        print(f"Max Drawdown:      {self.max_drawdown:.2%}")
        
        print("\n📈 TRADING ACTIVITY")
        print("-" * 80)
        print(f"Total Trades:      {len(trades)}")
        print(f"  BUY Orders:      {num_buys}")
        print(f"  SELL Orders:     {num_sells}")
        print(f"Total Fees:        ${total_fees:,.2f} USDC")
        print(f"Total Slippage:    ${total_slippage:,.2f} USDC")
        print(f"Win Rate:          {win_rate:.1f}% ({win_count}W / {loss_count}L)")
        print(f"Biggest Win:       ${biggest_win:+,.2f} USDC")
        print(f"Biggest Loss:      ${biggest_loss:+,.2f} USDC")
        
        print("\n🎯 OPPORTUNITY DETECTION")
        print("-" * 80)
        print(f"Total Detected:    {self.total_opportunities_found}")
        print(f"Total Approved:    {self.total_opportunities_approved}")
        print(f"Total Rejected:    {self.total_opportunities_rejected}")
        if self.total_opportunities_found > 0:
            approval_rate = (self.total_opportunities_approved / self.total_opportunities_found) * 100
            print(f"Approval Rate:     {approval_rate:.1f}%")
        
        print("\n📦 ACTIVE POSITIONS")
        print("-" * 80)
        if active_positions:
            print(f"Count:             {len(active_positions)}")
            for key, qty in active_positions.items():
                print(f"  {key}: {qty:.4f} shares")
        else:
            print("No active positions (all closed)")
        
        print("\n📁 REPORTS GENERATED")
        print("-" * 80)
        print(f"Trade Log:         {self.config.engine.report_path}")
        print(f"Unified Report:    reports/unified_report.json")
        print(f"Live Summary:      reports/live_summary.csv")
        
        print("\n" + "="*80)
        print("SESSION COMPLETE")
        print("="*80 + "\n")
        
        # Print verification commands
        print("🔍 VERIFICATION COMMANDS:")
        print("-" * 80)
        print("# View trade log:")
        print(f"  cat {self.config.engine.report_path}")
        print("\n# View unified report:")
        print("  python -m json.tool reports/unified_report.json | less")
        print("\n# Check invariants:")
        print("  # All balances should be non-negative")
        print("  # reserved_usdc should be 0 (all positions closed or tracked)")
        print("  # Sum of realized_pnl across trades should match wallet change")
        print("\n" + "="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Live paper-trading arbitrage bot (real-time data only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --duration 8                    # Run for 8 hours (default)
  %(prog)s --duration 0.5                  # Run for 30 minutes
  %(prog)s --capital 1000 --duration 4     # 1000 USDC for 4 hours
  %(prog)s --config custom.yml             # Use custom config

Stop Conditions:
  - Duration limit (--duration)
  - Drawdown limit (config: kill_switch_drawdown)
  - Manual interrupt (Ctrl+C)
        """
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=8.0,
        help="How long to run (hours). Default: 8.0"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=500.0,
        help="Starting capital (USDC). Default: 500.0"
    )
    parser.add_argument(
        "--config",
        default="config_live_paper.yml",
        help="Path to config file. Default: config_live_paper.yml"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level. Default: INFO"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Validate config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        print(f"   Expected: {config_path.absolute()}")
        sys.exit(1)
    
    # Create and run
    runner = LivePaperTradingRunner(
        config_path=str(config_path),
        duration_hours=args.duration,
        initial_capital=args.capital
    )
    runner.run()


if __name__ == "__main__":
    main()
