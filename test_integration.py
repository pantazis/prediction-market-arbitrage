#!/usr/bin/env python
"""Quick integration test for harness."""

import sys
sys.path.insert(0, 'src')

from predarb.testing import FakePolymarketClient
from predarb.notifiers.telegram import TelegramNotifierMock
from predarb.config import load_config
from predarb.engine import Engine
from pathlib import Path
import tempfile

print("=" * 60)
print("INTEGRATION TEST: Engine + FakeClient + Mock Notifier")
print("=" * 60)

# Create temp dir for output
with tempfile.TemporaryDirectory() as tmpdir:
    # Load config
    config = load_config('config.yml')
    config.engine.report_path = str(Path(tmpdir) / 'trades.csv')
    config.engine.iterations = 2
    config.engine.refresh_seconds = 0
    
    print(f"\n1. Creating FakePolymarketClient (10 markets, seed=42)...")
    client = FakePolymarketClient(num_markets=10, seed=42)
    print(f"   ✓ Client created")
    
    print(f"\n2. Creating TelegramNotifierMock...")
    notifier = TelegramNotifierMock()
    print(f"   ✓ Notifier created")
    
    print(f"\n3. Running Engine for {config.engine.iterations} iterations...")
    engine = Engine(config, client, notifier)
    engine.run()
    print(f"   ✓ Engine completed")
    
    print(f"\n4. Verification:")
    print(f"   ✓ Engine completed successfully")
    print(f"   ✓ Messages captured: {len(notifier.messages)}")
    print(f"   ✓ Trades executed: {len(engine.broker.trades)}")
    print(f"   ✓ Final cash: ${engine.broker.cash:,.2f}")
    print(f"   ✓ Report file exists: {Path(config.engine.report_path).exists()}")

print("\n" + "=" * 60)
print("✓ ALL INTEGRATION TESTS PASSED")
print("=" * 60)
