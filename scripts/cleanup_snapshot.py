#!/usr/bin/env python3
"""
Clean up markets_snapshot.json by removing expired markets.
Usage: python scripts/cleanup_snapshot.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def cleanup_snapshot(snapshot_path: str = "data/markets_snapshot.json", backup: bool = True):
    """
    Remove expired markets from snapshot file.
    
    Args:
        snapshot_path: Path to markets_snapshot.json
        backup: Whether to create a backup before cleaning
    """
    path = Path(snapshot_path)
    
    if not path.exists():
        print(f"❌ File not found: {snapshot_path}")
        return
    
    # Load current data
    print(f"📖 Loading {snapshot_path}...")
    with path.open("r", encoding="utf-8") as f:
        markets = json.load(f)
    
    original_count = len(markets)
    original_size_mb = path.stat().st_size / (1024 * 1024)
    print(f"   Found {original_count:,} markets ({original_size_mb:.1f} MB)")
    
    # Backup if requested
    if backup:
        backup_path = path.with_suffix(".json.bak")
        with backup_path.open("w", encoding="utf-8") as f:
            json.dump(markets, f, indent=2)
        print(f"💾 Backup saved to {backup_path}")
    
    # Filter out expired markets
    now = datetime.now(timezone.utc)
    active_markets = []
    
    for market in markets:
        end_date_str = market.get("end_date") or market.get("expiry")
        
        if not end_date_str:
            # No expiry date - keep it
            active_markets.append(market)
            continue
        
        try:
            # Parse ISO format datetime
            if end_date_str.endswith("Z"):
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            else:
                end_date = datetime.fromisoformat(end_date_str)
            
            # Keep if not expired
            if end_date > now:
                active_markets.append(market)
        except Exception as e:
            # Parse error - keep the market to be safe
            print(f"⚠️  Warning: couldn't parse date '{end_date_str}' for market {market.get('id')}: {e}")
            active_markets.append(market)
    
    removed_count = original_count - len(active_markets)
    
    if removed_count == 0:
        print("✅ No expired markets found. File is clean!")
        return
    
    # Save cleaned data
    print(f"🗑️  Removing {removed_count:,} expired markets...")
    with path.open("w", encoding="utf-8") as f:
        json.dump(active_markets, f, indent=2)
    
    new_size_mb = path.stat().st_size / (1024 * 1024)
    savings_mb = original_size_mb - new_size_mb
    savings_pct = (savings_mb / original_size_mb) * 100 if original_size_mb > 0 else 0
    
    print(f"✅ Cleanup complete!")
    print(f"   Markets: {original_count:,} → {len(active_markets):,} (-{removed_count:,})")
    print(f"   Size: {original_size_mb:.1f} MB → {new_size_mb:.1f} MB (-{savings_mb:.1f} MB, {savings_pct:.1f}%)")


if __name__ == "__main__":
    cleanup_snapshot()
