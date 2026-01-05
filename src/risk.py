from src.models import Opportunity, Market
from src.config import RiskConfig
import logging

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config
        self.open_markets = set()

    def check(self, opportunity: Opportunity, market: Market) -> bool:
        """
        Returns True if the opportunity is safe to execute.
        """
        
        # 1. Check liquidity
        if market.liquidity < self.config.min_liquidity:
            logger.info(f"Skipping {market.id}: Low liquidity ({market.liquidity} < {self.config.min_liquidity})")
            return False

        # 2. Check edge threshold
        if opportunity.estimated_edge < self.config.min_edge:
             logger.info(f"Skipping {market.id}: Edge too small ({opportunity.estimated_edge} < {self.config.min_edge})")
             return False
        
        # 3. Max open markets (simple check)
        if len(self.open_markets) >= self.config.max_open_markets and market.id not in self.open_markets:
             logger.info(f"Skipping {market.id}: Max open markets reached")
             return False

        return True

    def record_trade(self, market_id: str):
        self.open_markets.add(market_id)
