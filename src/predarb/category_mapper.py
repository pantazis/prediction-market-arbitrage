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
    def __init__(self, map_file: str = "data/category_map.csv"):
        self.map_file = Path(map_file)
        self.bucket_map: Dict[str, str] = {} # keyword -> bucket
        self.buckets: Set[str] = set()
        
        self._load_map()

    def _load_map(self):
        if not self.map_file.exists():
            print(f"Warning: Category map file {self.map_file} not found.")
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
            
        # Maybe check title words if heavily needed, but tags/category usually suffice
        # For Kalshi, market.category is often the series name or similar.
        
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
            # If we assume strict filtering, we might return False.
            # But "OTHER" matches "OTHER" is risky. 
            # Let's say False if either is OTHER for safety in this strict mode.
            return False
            
        return b1 == b2
