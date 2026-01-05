import logging
from typing import Optional
from datetime import datetime
from src.models import Trade, Opportunity

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Sends notifications to Telegram using the Bot API.
    Handles trade alerts, opportunity alerts, balance updates, and errors.
    """
    
    def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
        """
        Initialize the Telegram notifier.
        
        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Chat ID to send messages to
            enabled: Whether notifications are enabled
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.bot = None
        
        # Disable if credentials are missing
        if not bot_token or not chat_id:
            self.enabled = False
            logger.info("Telegram notifier disabled (missing credentials)")
            return
        
        self.enabled = enabled
        
        if self.enabled:
            try:
                from telegram import Bot
                self.bot = Bot(token=bot_token)
                logger.info("Telegram notifier initialized successfully")
            except ImportError:
                logger.error("python-telegram-bot not installed. Install with: pip install python-telegram-bot")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                self.enabled = False
        else:
            logger.info("Telegram notifier disabled")
    
    def _send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """
        Send a message to Telegram.
        
        Args:
            text: Message text
            parse_mode: Parse mode (Markdown or HTML)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.bot:
            return False
        
        try:
            import asyncio
            # Run async send in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
            )
            loop.close()
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def notify_trade(self, trade: Trade, market_title: str = "") -> bool:
        """
        Send a trade execution notification.
        
        Args:
            trade: The executed trade
            market_title: Optional market title for context
            
        Returns:
            True if notification sent successfully
        """
        side_emoji = "🟢" if trade.side == "BUY" else "🔴"
        
        message = f"""
{side_emoji} *Trade Executed*

*Market:* {market_title or trade.market_id}
*Side:* {trade.side}
*Amount:* {trade.amount:.4f}
*Price:* ${trade.price:.4f}
*Fees:* ${trade.fees:.4f}
*Total:* ${(trade.amount * trade.price + trade.fees):.2f}
*Time:* {trade.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self._send_message(message.strip())
    
    def notify_opportunity(self, opportunity: Opportunity) -> bool:
        """
        Send an arbitrage opportunity alert.
        
        Args:
            opportunity: The detected opportunity
            
        Returns:
            True if notification sent successfully
        """
        message = f"""
💰 *Arbitrage Opportunity Detected*

*Market:* {opportunity.market_title}
*Type:* {opportunity.type_name}
*Edge:* {opportunity.estimated_edge * 100:.2f}%
*Capital Required:* ${opportunity.required_capital:.2f}

*Description:* {opportunity.description}

*Actions:*
"""
        for i, action in enumerate(opportunity.actions, 1):
            message += f"\n{i}. {action.side} {action.amount:.2f} @ ${action.max_price:.4f}"
        
        message += f"\n\n*Time:* {opportunity.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())
    
    def notify_balance(self, cash: float, positions: dict, total_trades: int) -> bool:
        """
        Send a balance/portfolio update.
        
        Args:
            cash: Current cash balance
            positions: Dictionary of positions (outcome_id -> amount)
            total_trades: Total number of trades executed
            
        Returns:
            True if notification sent successfully
        """
        message = f"""
💼 *Portfolio Update*

*Cash:* ${cash:.2f}
*Total Trades:* {total_trades}
*Open Positions:* {len(positions)}
"""
        
        if positions:
            message += "\n*Positions:*\n"
            for outcome_id, amount in list(positions.items())[:5]:  # Show max 5
                message += f"  • {outcome_id}: {amount:.2f}\n"
            if len(positions) > 5:
                message += f"  ... and {len(positions) - 5} more\n"
        
        message += f"\n*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())
    
    def notify_error(self, error_message: str, context: str = "") -> bool:
        """
        Send an error notification.
        
        Args:
            error_message: The error message
            context: Optional context about where the error occurred
            
        Returns:
            True if notification sent successfully
        """
        message = f"""
⚠️ *Error Alert*

*Context:* {context or "General"}
*Error:* {error_message}

*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self._send_message(message.strip())
    
    def notify_startup(self, config_summary: str = "") -> bool:
        """
        Send a bot startup notification.
        
        Args:
            config_summary: Optional configuration summary
            
        Returns:
            True if notification sent successfully
        """
        message = f"""
🚀 *Bot Started*

The arbitrage bot has started successfully.

{config_summary}

*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self._send_message(message.strip())
