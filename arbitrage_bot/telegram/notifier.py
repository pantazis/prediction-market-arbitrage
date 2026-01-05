"""
Telegram notification system with granular control.

Handles sending notifications to Telegram with support for:
- Notification categories
- Granular enable/disable
- Wildcard disable
- Silent mode
"""
import logging
import asyncio
from typing import Optional, List
from abc import ABC, abstractmethod
from datetime import datetime

from ..config.schema import NotificationSettings, NotificationLevel

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract base for notification channels."""
    
    @abstractmethod
    async def send(self, message: str, category: str) -> bool:
        """
        Send a notification.
        
        Args:
            message: Message text (markdown format)
            category: Message category
            
        Returns:
            True if sent successfully
        """
        pass


class TelegramChannel(NotificationChannel):
    """Telegram notification channel."""
    
    def __init__(
        self,
        chat_id: str,
        topic_id: Optional[str] = None,
        send_callback=None,
    ):
        """
        Initialize Telegram channel.
        
        Args:
            chat_id: Target chat ID
            topic_id: Optional topic ID (for groups)
            send_callback: Async callback to actually send message
        """
        self.chat_id = chat_id
        self.topic_id = topic_id
        self.send_callback = send_callback
    
    async def send(self, message: str, category: str) -> bool:
        """Send notification via Telegram."""
        if not self.send_callback:
            logger.warning("No send_callback configured for TelegramChannel")
            return False
        
        try:
            await self.send_callback(
                chat_id=self.chat_id,
                topic_id=self.topic_id,
                text=message,
            )
            logger.debug(f"Notification sent: {category}")
            return True
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False


class LogChannel(NotificationChannel):
    """Log-based notification channel (for testing/fallback)."""
    
    def __init__(self, logger_instance=None):
        """Initialize log channel."""
        self.logger = logger_instance or logger
    
    async def send(self, message: str, category: str) -> bool:
        """Log notification."""
        self.logger.info(f"[{category}] {message}")
        return True


class Notifier:
    """
    Central notification router.
    
    Manages notification channels, respects settings, and ensures
    notifications only go out when appropriate.
    """
    
    def __init__(
        self,
        settings: NotificationSettings,
        channels: Optional[List[NotificationChannel]] = None,
    ):
        """
        Initialize notifier.
        
        Args:
            settings: NotificationSettings for control
            channels: List of notification channels to use
        """
        self.settings = settings
        self.channels = channels or [LogChannel()]
        self.sent_count = 0
        self.suppressed_count = 0
    
    async def notify(
        self,
        category: str,
        message: str,
        force: bool = False,
    ) -> bool:
        """
        Send a notification if appropriate.
        
        Args:
            category: Message category (e.g., "execution", "risk")
            message: Message text (markdown format)
            force: If True, bypass settings and send anyway
            
        Returns:
            True if sent to any channel
        """
        # Check if notification is enabled
        if not force and not self.settings.should_notify(category):
            self.suppressed_count += 1
            return False
        
        # Send to all channels
        results = []
        for channel in self.channels:
            try:
                result = await channel.send(message, category)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in channel notification: {e}")
                results.append(False)
        
        success = any(results)
        if success:
            self.sent_count += 1
        
        return success
    
    async def notify_startup(self, mode: str, uptime: str = "0s"):
        """Bot startup."""
        message = f"🚀 Bot started in {mode} mode (uptime: {uptime})"
        await self.notify("startup", message)
    
    async def notify_shutdown(self):
        """Bot shutdown."""
        message = "🛑 Bot stopped"
        await self.notify("startup", message)
    
    async def notify_warning(self, text: str):
        """Warning message."""
        message = f"⚠️ {text}"
        await self.notify("warning", message)
    
    async def notify_opportunity(
        self,
        edge_pct: float,
        event: str,
        venue_a: str,
        venue_b: str,
    ):
        """Opportunity detected."""
        message = f"🎯 Opportunity: {event}\n{venue_a} vs {venue_b}\nEdge: {edge_pct:.2f}%"
        await self.notify("scan_opportunity", message)
    
    async def notify_execution(
        self,
        position_id: str,
        size: float,
        cost: float,
    ):
        """Order executed."""
        message = f"📤 Execution: {position_id}\nSize: {size} USDC\nCost: {cost:.2f}"
        await self.notify("execution", message)
    
    async def notify_fill(
        self,
        order_id: str,
        qty: float,
        price: float,
    ):
        """Order filled."""
        message = f"✅ Fill: {order_id}\n{qty} @ {price:.4f}"
        await self.notify("fill", message)
    
    async def notify_hedge(
        self,
        position_id: str,
        status: str,
        reason: str = "",
    ):
        """Hedge executed or failed."""
        emoji = "🛡️" if status == "success" else "❌"
        message = f"{emoji} Hedge {position_id}: {status}"
        if reason:
            message += f"\n{reason}"
        await self.notify("hedge", message)
    
    async def notify_risk(self, text: str):
        """Risk limit hit or inventory low."""
        message = f"⛔ {text}"
        await self.notify("risk", message)
    
    async def notify_pnl_update(
        self,
        period: str,
        realized: float,
        unrealized: float,
    ):
        """Periodic PnL update."""
        message = (
            f"📊 {period.upper()} PnL\n"
            f"Realized: ${realized:+.2f}\n"
            f"Unrealized: ${unrealized:+.2f}"
        )
        await self.notify("pnl_update", message)
    
    async def notify_snapshot(self, snapshot_md: str):
        """Full state snapshot."""
        message = f"📸 State Snapshot\n```\n{snapshot_md}\n```"
        await self.notify("show_snapshot", message)
    
    async def notify_custom(self, text: str):
        """Custom message from strategy."""
        await self.notify("strategy_msg", text)
    
    def stats(self) -> dict:
        """Get notifier statistics."""
        return {
            "sent_count": self.sent_count,
            "suppressed_count": self.suppressed_count,
            "channels": len(self.channels),
        }
