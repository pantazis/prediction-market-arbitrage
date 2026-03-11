"""
Category Inferrer module.

Infers market category from question and description text when tags are empty.
Used as a fallback when Polymarket markets have no tags or category set.
"""

from typing import Optional

from predarb.models import Market


class CategoryInferrer:
    """
    Infers category from market question and description using keyword matching.
    
    When a market has empty tags and null category, this class analyzes the
    market question and description text to assign an appropriate category.
    """
    
    KEYWORD_CATEGORIES = {
        "CRYPTO": [
            "bitcoin", "ethereum", "btc", "eth", "crypto", "token", "defi", "nft"
        ],
        "POLITICS": [
            "president", "election", "congress", "senate", "vote", "trump", 
            "biden", "republican", "democrat"
        ],
        "ECONOMICS": [
            "fed", "inflation", "cpi", "interest rate", "gdp", "unemployment",
            "fomc", "treasury"
        ],
        "SPORTS": [
            "nfl", "nba", "mlb", "nhl", "super bowl", "championship", "playoffs"
        ],
    }
    
    def __init__(self, rolling_logger=None):
        """
        Initialize the CategoryInferrer.
        
        Args:
            rolling_logger: Optional logger for debugging inference decisions.
        """
        self.rolling_logger = rolling_logger
        # Build reverse lookup for efficient keyword matching
        self._keyword_to_category = {}
        for category, keywords in self.KEYWORD_CATEGORIES.items():
            for keyword in keywords:
                self._keyword_to_category[keyword.lower()] = category
    
    def infer(self, market: Market) -> str:
        """
        Infer category from market question and description.
        
        Checks the market question and description text for known keywords
        and returns the corresponding category. Returns "OTHER" when no
        category can be inferred.
        
        Args:
            market: The Market object to infer category for.
            
        Returns:
            Category string: "CRYPTO", "POLITICS", "ECONOMICS", "SPORTS", or "OTHER"
        """
        # Combine question and description for searching
        text_parts = []
        if market.question:
            text_parts.append(market.question)
        if market.description:
            text_parts.append(market.description)
        
        search_text = " ".join(text_parts).lower()
        
        if not search_text.strip():
            if self.rolling_logger:
                self.rolling_logger.debug(
                    "CATEGORY_INFER", 
                    f"Market {market.id}: No text to analyze, returning OTHER"
                )
            return "OTHER"
        
        # Check for keyword matches
        for category, keywords in self.KEYWORD_CATEGORIES.items():
            for keyword in keywords:
                if keyword.lower() in search_text:
                    if self.rolling_logger:
                        self.rolling_logger.debug(
                            "CATEGORY_INFER",
                            f"Market {market.id}: Found keyword '{keyword}' -> {category}"
                        )
                    return category
        
        if self.rolling_logger:
            self.rolling_logger.debug(
                "CATEGORY_INFER",
                f"Market {market.id}: No keywords matched, returning OTHER"
            )
        return "OTHER"
    
    def should_infer(self, market: Market) -> bool:
        """
        Check if category inference is needed for this market.
        
        Returns True if the market has empty tags and null category,
        indicating that inference should be attempted.
        
        Args:
            market: The Market object to check.
            
        Returns:
            True if inference is needed, False otherwise.
        """
        has_tags = bool(market.tags)
        has_category = market.category is not None
        return not has_tags and not has_category
    
    def infer_if_needed(self, market: Market) -> str:
        """
        Infer category only if the market lacks tags and category.
        
        If the market already has a category set, returns that category.
        If the market has tags but no category, returns "OTHER" (let CategoryMapper handle it).
        Otherwise, performs inference.
        
        Args:
            market: The Market object to process.
            
        Returns:
            Category string.
        """
        if market.category:
            return market.category.upper()
        
        if market.tags:
            # Has tags but no category - let CategoryMapper handle via tags
            return "OTHER"
        
        return self.infer(market)
