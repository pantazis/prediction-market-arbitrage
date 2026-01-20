
import logging
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add src to path
import os
sys.path.append(os.path.join(os.getcwd(), "src"))

from predarb.watchlist import scan_watchlist, WatchlistRow, ScanOutput
from predarb.config import WatchlistConfig

from predarb.models import Market, Outcome
from predarb.ab_filters import Quote

# Setup logging
logging.basicConfig(level=logging.INFO)

class TestWatchlistScan(unittest.TestCase):
    def setUp(self):
        self.mock_fetcher = MagicMock()
        self.mock_risk = MagicMock()
        self.mock_risk.approve.return_value = True
        
        self.config = WatchlistConfig(
            enabled=True,
            csv_path="dummy.csv",
            scan_log_path="dummy_scan.log",
            reject_log_path="dummy_reject.log",
            approve_log_path="dummy_approve.log",
            min_edge=0.01,
            min_depth_usd=50.0,
            max_age_sec=60,
            depth_fraction=0.1,
            orderbook_enabled=True
        )

    @patch("predarb.watchlist.evaluate_ab_filters")
    def test_scan_watchlist_arbitrage(self, mock_evaluate):
        # Setup passed filter report
        mock_report = MagicMock()
        mock_report.passed = True
        mock_report.edge_net = 0.05
        mock_evaluate.return_value = mock_report
        
        # Setup mock fetcher to return valid orderbooks
        # Returns (kalshi_ob, polymarket_ob, latency)
        # Mock the fetcher to return different dicts based on call args
        def fetcher_side_effect(venue, market, outcome):
            if venue == "kalshi":
                return {"bids": [{"price": 0.60, "size": 1000}], "asks": [{"price": 0.62, "size": 1000}]}
            else:
                return {"bids": [{"price": 0.48, "size": 1000}], "asks": [{"price": 0.50, "size": 1000}]}
        
        self.mock_fetcher.side_effect = fetcher_side_effect
        
        row = WatchlistRow(
            pair_id="test_pair",
            k_ticker="K1",
            p_market_id="P1",
            p_yes_token_id="Y1",
            p_no_token_id="N1",
            polarity="normal",
            k_question="Q1",
            p_question="Q2",
            k_expiration_time="2026-01-01T00:00:00Z",
            p_endDate="2026-01-01T00:00:00Z",
            min_edge=0.01,
            min_depth_usd=50.0,
            max_age_sec=60,
            status="active",
            last_verified_at="2026-01-01T00:00:00Z"
        )
        
        # Mock Engine lists
        # Need dummy markets for metadata lookup
        k_market = Market(id="K1", exchange="kalshi", title="K Title", outcomes=[Outcome(id="YES", label="Yes", price=0.6), Outcome(id="NO", label="No", price=0.4)])
        p_market = Market(id="P1", exchange="polymarket", title="P Title", outcomes=[Outcome(id="Y1", label="Yes", price=0.5), Outcome(id="N1", label="No", price=0.5)])
        
        output = scan_watchlist(
            rows=[row],
            kalshi_markets=[k_market],
            polymarket_markets=[p_market],
            orderbook_fetcher=self.mock_fetcher,
            depth_fraction=0.1
        )
        
        print("\n--- TEST RESULT ---")
        print(f"Approve packets found: {len(output.approve_packets)}")
        if len(output.approve_packets) > 0:
            print(f"Packet 1: {output.approve_packets[0]}")
            print("✅ Watchlist scan logic CONFIRMED working.")
        else:
            print("❌ Watchlist scan logic FAILED to find opportunity.")
            print(f"Rejects: {output.rejects}")
            
        self.assertTrue(len(output.approve_packets) > 0)
        # self.mock_fetcher.fetch_latest_for_pair.assert_called() # Not called directly

if __name__ == '__main__':
    unittest.main()
