from __future__ import annotations

import logging
from typing import Optional

import requests

from predarb.models import Opportunity

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _post(self, text: str):
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    def notify_startup(self, message: str):
        self._post(f"📈 Predarb started\n{message}")

    def notify_error(self, message: str, context: Optional[str] = None):
        prefix = f"❗ Error in {context}: " if context else "❗ Error: "
        self._post(prefix + message)

    def notify_opportunity(self, opp: Opportunity):
        # Classify opportunity quality based on edge
        edge_pct = opp.net_edge * 100
        if edge_pct >= 5.0:
            status = "🟢 GREAT"
        elif edge_pct >= 2.0:
            status = "🟡 MEDIUM"
        else:
            status = "🔴 BAD"
        
        # Format edge as percentage with gains estimate
        edge_str = f"{edge_pct:.2f}%"
        
        # Estimate profit in dollars (assuming $100 trade size for reference)
        estimated_gain = opp.net_edge * 100
        gain_str = f"${estimated_gain:.2f} per $100"
        
        # Get market titles from metadata if available
        market_titles = opp.metadata.get("market_titles", [])
        if market_titles:
            # Show first title, or indicate multiple
            if len(market_titles) == 1:
                title_str = market_titles[0][:80] + "..." if len(market_titles[0]) > 80 else market_titles[0]
            else:
                title_str = f"{market_titles[0][:60]}... (+{len(market_titles)-1} more)"
        else:
            title_str = None
        
        # Format market IDs (shorten if they're hashes)
        market_ids = opp.market_ids
        if len(market_ids) > 0 and len(market_ids[0]) > 20:
            # Likely hashes, show shortened version
            markets_str = ", ".join([m[:8] + "..." + m[-6:] for m in market_ids])
        else:
            markets_str = ", ".join(market_ids)
        
        # Format trade actions (BUY/SELL sides)
        actions_str = []
        for i, action in enumerate(opp.actions, 1):
            side_emoji = "📗" if action.side.upper() == "BUY" else "📕"
            # Try to show outcome ID in a readable way
            outcome = action.outcome_id if len(action.outcome_id) <= 8 else action.outcome_id[:6] + "..."
            actions_str.append(f"{side_emoji} {action.side} {outcome} @ {action.limit_price:.3f}")
        trades_str = " vs ".join(actions_str) if len(actions_str) <= 3 else f"{len(actions_str)} trades"
        
        lines = [
            f"🔎 Opportunity {opp.type} {status}",
        ]
        if title_str:
            lines.append(f"Market: {title_str}")
        lines.extend([
            f"Trades: {trades_str}",
            f"IDs: {markets_str}",
            f"Edge: {edge_str} (Est. gain: {gain_str})",
            f"Details: {opp.description}",
        ])
        self._post("\n".join(lines))

    def notify_trade_summary(self, count: int):
        self._post(f"✅ Executed {count} opportunities this iteration.")

    def notify_filtering(self, total: int, eligible: int, ranked: int, high_quality: int):
        lines = [
            "🔍 Market Filtering Results",
            f"Total markets: {total}",
            f"Eligible markets: {eligible}",
            f"Ranked markets: {ranked}",
            f"High-quality markets: {high_quality}",
        ]
        self._post("\n".join(lines))
