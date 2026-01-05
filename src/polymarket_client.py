from typing import List, Protocol, Optional
import requests
import logging
from datetime import datetime
from src.models import Market, Outcome

logger = logging.getLogger(__name__)

class PolymarketClient(Protocol):
    def get_active_markets(self) -> List[Market]:
        ...

class HttpPolymarketClient:
    def __init__(self, base_url: str = "https://gamma-api.polymarket.com"):
        self.base_url = base_url.rstrip('/')

    def get_active_markets(self) -> List[Market]:
        """
        Fetches active markets. 
        Note: The simplified endpoint logic here assumes we can query for active events.
        """
        url = f"{self.base_url}/events"
        params = {
            "closed": "false",
            "limit": 100, # Simplified pagination
            "offset": 0
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            markets = []
            # Gamma structure usually returns a list of events, each with 'markets' inside
            for event in data:
                if not isinstance(event, dict): 
                    continue
                    
                event_markets = event.get('markets', [])
                for m_data in event_markets:
                    try:
                        m = self._parse_market(m_data, event.get('title', 'Unknown'))
                        if m:
                            markets.append(m)
                    except Exception as e:
                        logger.warning(f"Failed to parse market {m_data.get('id')}: {e}")
            
            return markets
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    def _parse_market(self, data: dict, event_title: str) -> Optional[Market]:
        # Minimal parsing logic based on typical Gamma API structure
        if data.get('closed', False):
            return None
            
        outcomes_raw = data.get('outcomes', [])
        prices_raw = data.get('outcomePrices', [])
        
        # Gamma API sometimes sends json encoded strings for outcomes
        import json
        if isinstance(outcomes_raw, str):
            try:
                outcomes_raw = json.loads(outcomes_raw)
            except:
                outcomes_raw = []
        
        if isinstance(prices_raw, str):
             try:
                prices_raw = json.loads(prices_raw)
             except:
                prices_raw = []

        if not outcomes_raw or len(outcomes_raw) != len(prices_raw):
            return None

        outcomes = []
        for i, label in enumerate(outcomes_raw):
            # Price might be string
            try:
                price = float(prices_raw[i])
            except (ValueError, TypeError):
                price = 0.0
                
            outcomes.append(Outcome(
                id=f"{data.get('id')}_{i}", # outcome IDs often separate, but using synthetic for simplicity if needed
                label=str(label),
                price=price
            ))

        # Date parsing
        end_date = None
        if data.get('endDate'):
            try:
                # ISO format often used
                end_date = datetime.fromisoformat(data['endDate'].replace('Z', '+00:00'))
            except:
                pass

        return Market(
            id=str(data.get('id')),
            question=data.get('question', event_title),
            outcomes=outcomes,
            end_date=end_date,
            liquidity=float(data.get('liquidity', 0.0) or 0.0),
            volume=float(data.get('volume', 0.0) or 0.0),
            description=data.get('description', '')
        )
