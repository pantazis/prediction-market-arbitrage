"""Simulation harness entry point for manual simulation runs.

Runs the arbitrage bot against a fake Polymarket data source with real Telegram notifications.

Example:
    python -m sim_run --days 2 --trade-size 200 --seed 42

Environment Variables:
    TELEGRAM_BOT_TOKEN: Telegram bot token (required for real Telegram messages)
    TELEGRAM_CHAT_ID: Telegram chat ID (required for real Telegram messages)
"""

import argparse
import logging
import sys
from pathlib import Path

from predarb.config import AppConfig, load_config
from predarb.engine import Engine
from predarb.notifiers.telegram import TelegramNotifierReal
from predarb.testing import FakePolymarketClient

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    """Main entry point for simulation harness."""
    parser = argparse.ArgumentParser(
        description="Run arbitrage bot against fake Polymarket data with real Telegram notifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 2-day simulation with $200 per trade
  python -m sim_run --days 2 --trade-size 200

  # Run with custom config and seed
  python -m sim_run --config config.yml --days 2 --seed 42

  # Run with verbose logging
  python -m sim_run --days 2 -v
        """,
    )

    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Number of days to simulate (default: 2)",
    )
    parser.add_argument(
        "--trade-size",
        type=float,
        default=500.0,
        help="Target trade size in USD (default: 500.0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic market generation (default: 42)",
    )
    parser.add_argument(
        "--markets",
        type=int,
        default=30,
        help="Number of markets to generate (default: 30)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yml",
        help="Path to config YAML (default: config.yml)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Disable real Telegram notifications (use for testing without credentials)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger.info("=" * 80)
    logger.info("PREDICTION MARKET ARBITRAGE SIMULATION HARNESS")
    logger.info("=" * 80)
    logger.info(f"Days: {args.days}")
    logger.info(f"Trade Size: ${args.trade_size}")
    logger.info(f"Seed: {args.seed}")
    logger.info(f"Markets: {args.markets}")
    logger.info(f"Config: {args.config}")
    logger.info(f"Telegram Enabled: {not args.no_telegram}")
    logger.info("=" * 80)

    try:
        # Load configuration
        if not Path(args.config).exists():
            logger.error(f"Config file not found: {args.config}")
            sys.exit(1)

        config = load_config(args.config)
        logger.info(f"Loaded config from {args.config}")

        # Create fake Polymarket client
        fake_client = FakePolymarketClient(
            num_markets=args.markets,
            days=args.days,
            seed=args.seed,
        )
        logger.info(f"Created FakePolymarketClient: {args.markets} markets, {args.days} days")

        # Create notifier
        notifier = None
        if not args.no_telegram:
            try:
                notifier = TelegramNotifierReal()
                logger.info("Initialized TelegramNotifierReal")
                # Send startup message
                notifier.send(
                    f"📈 Arbitrage bot simulation started\n"
                    f"Days: {args.days}\n"
                    f"Markets: {args.markets}\n"
                    f"Seed: {args.seed}"
                )
            except ValueError as e:
                logger.error(f"Failed to initialize Telegram: {e}")
                logger.error("Provide TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
                sys.exit(1)
        else:
            logger.info("Telegram disabled (--no-telegram flag)")

        # Create and run engine
        engine = Engine(config, fake_client, notifier)
        logger.info("Initialized Engine with FakePolymarketClient")

        # Configure for simulation
        engine.config.engine.iterations = args.days * 24 * 60  # One iteration per minute
        logger.info(f"Running {engine.config.engine.iterations} iterations ({args.days} days @ 1 min/iteration)")

        # Run simulation
        logger.info("Starting simulation...")
        engine.run()

        logger.info("=" * 80)
        logger.info("SIMULATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Cash remaining: ${engine.broker.cash:.2f}")
        logger.info(f"Trades executed: {len(engine.broker.trades)}")
        logger.info(f"Report written to: {engine.report_path}")

        # Send final summary via Telegram
        if notifier:
            final_pnl = engine.broker.cash - engine.config.broker.initial_cash
            notifier.send(
                f"✅ Simulation complete\n"
                f"Trades executed: {len(engine.broker.trades)}\n"
                f"Initial cash: ${engine.config.broker.initial_cash:.2f}\n"
                f"Final cash: ${engine.broker.cash:.2f}\n"
                f"Net PnL: ${final_pnl:+.2f}"
            )

    except Exception as e:
        logger.exception(f"Simulation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
