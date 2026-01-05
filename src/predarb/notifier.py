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
        lines = [
            f"🔎 Opportunity {opp.type}",
            f"Markets: {', '.join(opp.market_ids)}",
            f"Edge: {opp.net_edge:.4f}",
            f"Details: {opp.description}",
        ]
        self._post("\n".join(lines))

    def notify_trade_summary(self, count: int):
        self._post(f"✅ Executed {count} opportunities this iteration.")
