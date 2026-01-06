"""Notifier interface and implementations for arbitrage bot messaging.

Provides two notifier implementations:
  - TelegramNotifierReal: sends to real Telegram using bot token + chat_id
  - TelegramNotifierMock: stores messages in memory for unit tests

Both implement the Notifier interface: send(text: str) -> None
"""

from abc import ABC, abstractmethod
from typing import List


class Notifier(ABC):
    """Abstract base class for all notifiers."""

    @abstractmethod
    def send(self, text: str) -> None:
        """Send a message to the notification channel.
        
        Args:
            text: Message text to send
        """
        pass


__all__ = ["Notifier"]
