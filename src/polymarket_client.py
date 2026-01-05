from typing import List, Protocol, Optional, Any
import requests
import logging
from datetime import datetime
from src.models import Market, Outcome
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from src.config import PolymarketConfig

logger = logging.getLogger(__name__)

class PolymarketClient(Protocol):
    def get_active_markets(self) -> List[Market]:
        ...

class ClobPolymarketClient:
    def __init__(self, config: PolymarketConfig):
        self.config = config
        
        creds = None
        if config.api_key and config.secret and config.passphrase:
            creds = ApiCreds(
                api_key=config.api_key,
                api_secret=config.secret,
                api_passphrase=config.passphrase
            )

        self.client = ClobClient(
            host=config.host,
            key=config.key if config.key else None,
            chain_id=config.chain_id,
            creds=creds,
            signature_type=1, # Defaulting to 1 (e.g. derived/custodial)
            funder=config.funder if config.funder else None
        )

    def get_active_markets(self) -> List[Market]:
        """
        Fetches active markets using the CLOB client.
        The CLOB client typically has methods like get_markets or get_sampling_markets.
        We'll use get_markets and filter/parse.
        """
        try:
            # next_cursor is used for pagination, here we just fetch one batch or loop if needed
            # For simplicity in this step, we fetch a simplified list or specific tokens if possible.
            # However, CLOB 'get_markets' might expect specific tokens. 
            # 'get_markets' in py-clob-client often returns a list of markets.
            # Checking library usage: client.get_markets(next_cursor="")
            
            resp = self.client.get_markets()
            
            # resp is typically a dictionary with 'data' and 'next_cursor'
            markets_data = resp.get('data', []) if isinstance(resp, dict) else resp

            markets = []
            for m_data in markets_data:
                try:
                    m = self._parse_market(m_data)
                    if m:
                        markets.append(m)
                except Exception as e:
                    logger.warning(f"Failed to parse clob market {m_data.get('condition_id')}: {e}")
            
            return markets
        except Exception as e:
            import traceback
            logger.error(f"Error fetching markets via CLOB: {e}")
            logger.debug(traceback.format_exc())
            return []

    def _parse_market(self, data: dict) -> Optional[Market]:
        # Clob market structure is different from Gamma.
        # It usually contains token_id, question, outcomes, etc.
        
        # Determine if active
        if data.get('active') is False or data.get('closed') is True:
             return None

        # Parse outcomes
        # CLOB API often returns 'tokens' list with outcome_id and price info
        tokens = data.get('tokens', [])
        
        outcomes = []
        for i, token in enumerate(tokens):
             price = float(token.get('price', 0.0))
             outcomes.append(Outcome(
                 id=token.get('token_id', f"{data.get('condition_id')}_{i}"),
                 label=token.get('outcome', str(i)),
                 price=price
             ))
        
        # If no outcomes or prices, skip
        if not outcomes:
            return None

        return Market(
            id=data.get('condition_id', str(data.get('question_id'))), # Use condition_id as unique stable ID usually
            question=data.get('question', 'Unknown Question'),
            outcomes=outcomes,
            end_date=None, # CLOB market data might not have friendly end_date, usually uses end_date_iso if avail
            liquidity=0.0, # detailed liquidity often requires separate calls (orderbook)
            volume=0.0,
            description=data.get('description', '')
        )


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
