"""Real and mock Telegram notifier implementations."""

import logging
import os
from typing import List, Optional

import requests

from predarb.notifiers import Notifier
from predarb.models import Opportunity

logger = logging.getLogger(__name__)


class TelegramNotifierReal(Notifier):
    """Sends messages to real Telegram using bot token and chat ID.
    
    Credentials are read from environment variables:
      - TELEGRAM_BOT_TOKEN: bot token for Telegram API
      - TELEGRAM_CHAT_ID: chat ID to send messages to
    
    Raises ValueError if credentials are missing.
    """

    # Sentinel to distinguish "argument omitted" vs "explicit None"
    _UNSET = object()

    def __init__(self, bot_token: Optional[str] = _UNSET, chat_id: Optional[str] = _UNSET):
        """Initialize TelegramNotifierReal.
        
        Args:
            bot_token: Telegram bot token (or None to read from TELEGRAM_BOT_TOKEN env var)
            chat_id: Telegram chat ID (or None to read from TELEGRAM_CHAT_ID env var)
        
        Raises:
            ValueError: If bot_token or chat_id are missing
        """
        # Explicit None should be treated as missing credentials and raise,
        # while omitted parameters may fall back to environment variables.
        if bot_token is None:
            self.bot_token = None
        elif bot_token is TelegramNotifierReal._UNSET:
            self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        else:
            self.bot_token = bot_token

        if chat_id is None:
            self.chat_id = None
        elif chat_id is TelegramNotifierReal._UNSET:
            self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        else:
            self.chat_id = chat_id
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required but not provided or set in environment")
        if not self.chat_id:
            raise ValueError("TELEGRAM_CHAT_ID is required but not provided or set in environment")
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send(self, text: str) -> None:
        """Send a message to Telegram.
        
        Args:
            text: Message text to send
        """
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=5,
            )
            resp.raise_for_status()
            logger.debug(f"Telegram message sent: {len(text)} chars")
        except Exception as e:
            # Don't raise - just log. Telegram failures shouldn't crash the bot
            logger.warning(f"Failed to send Telegram message: {type(e).__name__}: {e}")

    # Compatibility methods for predarb.notifier API
    def _post(self, text: str) -> None:
        """Internal method for backward compatibility."""
        self.send(text)

    def notify_startup(self, message: str) -> None:
        """Notify startup (compatibility method)."""
        self._post(f"📈 Predarb started\n{message}")

    def notify_error(self, message: str, context: Optional[str] = None) -> None:
        """Notify error (compatibility method)."""
        prefix = f"❗ Error in {context}: " if context else "❗ Error: "
        self._post(prefix + message)

    def notify_opportunity(self, opp: Opportunity) -> None:
        """Notify opportunity (compatibility method)."""
        lines = [
            f"🔎 Opportunity {opp.type}",
            f"Markets: {', '.join(opp.market_ids)}",
            f"Edge: {opp.net_edge:.4f}",
            f"Details: {opp.description}",
        ]
        self._post("\n".join(lines))

    def notify_trade_summary(self, count: int) -> None:
        """Notify trade summary (compatibility method)."""
        self._post(f"✅ Executed {count} opportunities this iteration.")

    def notify_filtering(self, total: int, eligible: int, ranked: int, high_quality: int) -> None:
        """Notify filtering results (compatibility method)."""
        lines = [
            "🔍 Market Filtering Results",
            f"Total markets: {total}",
            f"Eligible markets: {eligible}",
            f"Ranked markets: {ranked}",
            f"High-quality markets: {high_quality}",
        ]
        self._post("\n".join(lines))


class TelegramNotifierMock(Notifier):
    """Mock notifier that stores messages in memory for testing.
    
    Useful for unit tests that need to verify messages without hitting Telegram.
    """

    def __init__(self):
        """Initialize TelegramNotifierMock."""
        self.messages: List[str] = []

    def send(self, text: str) -> None:
        """Store message in memory.
        
        Args:
            text: Message text to store
        """
        self.messages.append(text)
        logger.debug(f"Mock notifier stored message: {len(text)} chars")

    def clear(self) -> None:
        """Clear all stored messages."""
        self.messages.clear()

    def get_messages(self) -> List[str]:
        """Get all stored messages.
        
        Returns:
            List of all messages sent via send()
        """
        return self.messages.copy()

    def has_message_containing(self, substring: str) -> bool:
        """Check if any stored message contains a substring.
        
        Args:
            substring: Text to search for in messages
        
        Returns:
            True if any message contains substring
        """
        return any(substring in msg for msg in self.messages)

    # Compatibility methods for predarb.notifier API
    def _post(self, text: str) -> None:
        """Internal method for backward compatibility."""
        self.send(text)

    def notify_startup(self, message: str) -> None:
        """Notify startup (compatibility method)."""
        self._post(f"📈 Predarb started\n{message}")

    def notify_error(self, message: str, context: Optional[str] = None) -> None:
        """Notify error (compatibility method)."""
        prefix = f"❗ Error in {context}: " if context else "❗ Error: "
        self._post(prefix + message)

    def notify_opportunity(self, opp: Opportunity) -> None:
        """Notify opportunity (compatibility method)."""
        lines = [
            f"🔎 Opportunity {opp.type}",
            f"Markets: {', '.join(opp.market_ids)}",
            f"Edge: {opp.net_edge:.4f}",
            f"Details: {opp.description}",
        ]
        self._post("\n".join(lines))

    def notify_trade_summary(self, count: int) -> None:
        """Notify trade summary (compatibility method)."""
        self._post(f"✅ Executed {count} opportunities this iteration.")

    def notify_filtering(self, total: int, eligible: int, ranked: int, high_quality: int) -> None:
        """Notify filtering results (compatibility method)."""
        lines = [
            "🔍 Market Filtering Results",
            f"Total markets: {total}",
            f"Eligible markets: {eligible}",
            f"Ranked markets: {ranked}",
            f"High-quality markets: {high_quality}",
        ]
        self._post("\n".join(lines))


__all__ = ["TelegramNotifierReal", "TelegramNotifierMock"]
