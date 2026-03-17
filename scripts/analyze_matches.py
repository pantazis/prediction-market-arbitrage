#!/usr/bin/env python3
"""
Continuous cross-venue match analyzer with rolling log.

Usage:
    python scripts/analyze_matches.py                    # Run once
    python scripts/analyze_matches.py --continuous       # Run every 5 min
    python scripts/analyze_matches.py -c --interval 60   # Every 60 sec
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from predarb.kalshi_client import KalshiClient
from predarb.config import PolymarketConfig
from predarb.polymarket_client import PolymarketClient
from predarb.match_pipeline import MatchPipeline
from predarb.ticker_parser import TickerParser
from predarb.extractors import ThresholdExtractor
from predarb.asset_normalizer import AssetNormalizer
from predarb.category_inferrer import CategoryInferrer

LOG_FILE = Path(__file__).parent.parent / "log" / "match_analysis.log"
MAX_LINES = 100


class RollingLog:
    """Rolling window log file."""
    
    def __init__(self, path: Path, max_lines: int = 100):
        self.path = path
        self.max_lines = max_lines
        self.lines = []
        if path.exists():
            self.lines = path.read_text().strip().split("\n")[-max_lines:]
    
    def write(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        self.lines.append(line)
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines:]
        print(line)
    
    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines))


def get_orderbook_price(kalshi, ticker: str) -> tuple:
    """Get YES/NO prices from Kalshi orderbook."""
    try:
        ob = kalshi.fetch_orderbook(ticker)
        if ob and "orderbook_fp" in ob:
            fp = ob["orderbook_fp"]
            no_orders = fp.get("no_dollars", [])
            if no_orders:
                no_ask = float(no_orders[0][0])
                return 1.0 - no_ask, no_ask  # yes_price, no_price
    except:
        pass
    return None, None


def get_poly_price(market) -> tuple:
    """Get YES/NO prices from Polymarket."""
    for o in market.outcomes:
        if getattr(o, "label", "").lower() == "yes":
            return o.price, 1.0 - o.price
    return None, None


def run_scan(log: RollingLog) -> bool:
    """Run one scan cycle. Returns True on success."""
    log.write("=" * 40)
    log.write("SCAN START")
    
    try:
        kalshi = KalshiClient()
        poly = PolymarketClient(PolymarketConfig(
            host="https://gamma-api.polymarket.com",
            clob_host="https://clob.polymarket.com",
            limit=500
        ))
    except Exception as e:
        log.write(f"ERROR init: {e}")
        return False
    
    try:
        all_k = kalshi.fetch_markets()
        k_btc = [m for m in all_k if "KXBTCD" in m.id]
        p_all = poly.fetch_markets()
        p_btc = [m for m in p_all if "bitcoin" in m.question.lower()]
        log.write(f"Markets: Kalshi={len(k_btc)} Poly={len(p_btc)}")
    except Exception as e:
        log.write(f"ERROR fetch: {e}")
        return False
    
    pipeline = MatchPipeline(
        ticker_parser=TickerParser(),
        threshold_extractor=ThresholdExtractor(),
        asset_normalizer=AssetNormalizer(),
        category_inferrer=CategoryInferrer(),
    )
    
    matches = pipeline.process(k_btc, p_btc)
    rej = pipeline.get_rejection_summary()
    log.write(f"Matches={len(matches)} | Rej: thresh={rej.get('threshold',0)} asset={rej.get('asset',0)}")
    
    # Analyze each match for arbitrage
    arb_count = 0
    for m in matches[:10]:
        k_data = pipeline._get_market_data(m.kalshi_market)
        ticker = m.kalshi_market.id.split(":")[-1]
        threshold = k_data["threshold"]
        
        k_yes, _ = get_orderbook_price(kalshi, ticker)
        p_yes, _ = get_poly_price(m.polymarket_market)
        
        if k_yes is None or p_yes is None:
            log.write(f"${threshold:,.0f}: NO PRICE DATA")
            continue
        
        spread = abs(k_yes - p_yes)
        
        # Check resolution time diff
        k_exp = m.kalshi_market.expiry
        p_exp = m.polymarket_market.expiry
        time_diff_h = abs((k_exp - p_exp).total_seconds()) / 3600 if k_exp and p_exp else 0
        
        if spread > 0.02:  # >2% spread
            if time_diff_h > 1:
                status = f"NO ARB (time diff {time_diff_h:.0f}h)"
            else:
                status = f">>> ARB {spread*100:.1f}% <<<"
                arb_count += 1
        else:
            status = f"no arb ({spread*100:.1f}%)"
        
        log.write(f"${threshold:,.0f}: K={k_yes:.2f} P={p_yes:.3f} | {status}")
    
    log.write(f"SCAN DONE: {arb_count} opportunities")
    log.write("=" * 40)
    return True


def main():
    parser = argparse.ArgumentParser(description="Cross-venue match analyzer")
    parser.add_argument("-c", "--continuous", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between scans (default: 300)")
    args = parser.parse_args()
    
    log = RollingLog(LOG_FILE, MAX_LINES)
    
    if args.continuous:
        log.write(f"Starting continuous mode (interval={args.interval}s)")
        while True:
            try:
                run_scan(log)
                log.save()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                log.write("Stopped by user")
                log.save()
                break
            except Exception as e:
                log.write(f"ERROR: {e}")
                log.save()
                time.sleep(60)  # Wait 1 min on error
    else:
        run_scan(log)
        log.save()


if __name__ == "__main__":
    main()
