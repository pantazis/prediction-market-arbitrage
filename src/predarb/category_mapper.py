"""
Category Mapper module.

Loads `data/category_map.csv` and provides functionality to map
Kalshi markets and Polymarket markets to high-level buckets (e.g., POLITICS, ECONOMICS).
This allows for "Politics vs Politics" strict filtering.
"""

import csv
from pathlib import Path
from typing import Dict, List, Set, Optional
from predarb.models import Market

class CategoryMapper:
    def __init__(self, map_file: str = "data/category_map.csv", rolling_logger=None):
        self.map_file = Path(map_file)
        self.bucket_map: Dict[str, str] = {} # keyword -> bucket
        self.buckets: Set[str] = set()
        self.rolling_logger = rolling_logger
        
        self._load_map()

    def _load_map(self):
        if not self.map_file.exists():
            print(f"Warning: Category map file {self.map_file} not found.")
            if self.rolling_logger:
                self.rolling_logger.warning("TAG_FILTER", f"Category map file {self.map_file} not found")
            return

        with self.map_file.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                bucket = row["bucket_name"].strip().upper()
                if not bucket:
                    continue
                self.buckets.add(bucket)

                # Kalshi keywords
                kalshi_tags = row.get("kalshi_category", "").split("|")
                for tag in kalshi_tags:
                    t = tag.strip().lower()
                    if t:
                        self.bucket_map[t] = bucket

                # Polymarket keywords
                poly_tags = row.get("polymarket_tag", "").split("|")
                for tag in poly_tags:
                    t = tag.strip().lower()
                    if t:
                        self.bucket_map[t] = bucket
        if self.rolling_logger:
            self.rolling_logger.info("TAG_FILTER", f"Loaded category map: {len(self.buckets)} buckets, {len(self.bucket_map)} keywords")
            
            # Detailed dump of the map for verification
            self.rolling_logger.info("TAG_FILTER", "--- CATEGORY MAP DUMP ---")
            
            # Re-read to log structure or reconstruct from loaded map (re-reading is cleaner for row-by-row logging)
            # Or better, just group our bucket_map by bucket for logging
            from collections import defaultdict
            bucket_groups = defaultdict(list)
            for k, v in self.bucket_map.items():
                bucket_groups[v].append(k)
            
            for bucket, keywords in sorted(bucket_groups.items()):
                self.rolling_logger.info("TAG_FILTER", f"BUCKET: {bucket}")
                # Log keywords in chunks of 10 to keep lines readable
                sorted_kws = sorted(keywords)
                for i in range(0, len(sorted_kws), 10):
                    chunk = ", ".join(sorted_kws[i:i+10])
                    self.rolling_logger.info("TAG_FILTER", f"  Tags: {chunk}")
            
            self.rolling_logger.info("TAG_FILTER", "--- END DUMP ---")
    
    def get_bucket(self, market: Market, source: str) -> str:
        """
        Determine the bucket for a market.
        source: 'kalshi' or 'polymarket'
        """
        # We search through the market's tags, category, or even title 
        # to find a matching keyword in our bucket_map.
        
        search_terms = set()
        
        # Add tags
        if market.tags:
            for t in market.tags:
                search_terms.add(str(t).lower())
        
        # Add category
        if market.category:
            search_terms.add(str(market.category).lower())
            
        # Add title keywords
        if market.question:
            # We add the full title to search terms.
            # The fallback loop (if keyword in term) will catch keywords inside the title.
            search_terms.add(str(market.question).lower())
        
        # Check against map
        # Priority: Exact match logic could be improved, but this is a greedy match
        for term in search_terms:
            if term in self.bucket_map:
                return self.bucket_map[term]
        
        # Fallback: Check if any keyword in map is a substring of terms
        # (This is slower, optimize if needed)
        for keyword, bucket in self.bucket_map.items():
            for term in search_terms:
                if keyword in term:
                    return bucket
                    
        return "OTHER"

    def are_compatible(self, m1: Market, source1: str, m2: Market, source2: str) -> bool:
        """
        Check if two markets belong to the same bucket.
        """
        b1 = self.get_bucket(m1, source1)
        b2 = self.get_bucket(m2, source2)
        
        if b1 == "OTHER" or b2 == "OTHER":
            # REVISION: User requested to EXCLUDE "OTHER" folder.
            # Strict filtering: We only match if both are known and identical.
            if self.rolling_logger:
                self.rolling_logger.debug("TAG_FILTER", f"Rejected: {m1.id} ({b1}) <-> {m2.id} ({b2}) - excluding OTHER bucket")
            return False
        
        compatible = b1 == b2
        if self.rolling_logger and not compatible:
            self.rolling_logger.debug("TAG_FILTER", f"Rejected: {m1.id} ({b1}) <-> {m2.id} ({b2}) - category mismatch")
            
        return compatible
