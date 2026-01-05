"""
Main entry point for the Telegram-controlled arbitrage bot.

This demonstrates how to integrate the Telegram interface with the actual bot loop.
"""
import asyncio
import logging
import json
import os
from pathlib import Path
from typing import Optional, Callable

from arbitrage_bot.core.control_queue import ControlQueue
from arbitrage_bot.core.bot_loop import BotLoop
from arbitrage_bot.core.state import BotSnapshot
from arbitrage_bot.config.schema import TelegramConfig, TelegramConfigLoader
from arbitrage_bot.telegram.router import CommandRouter, CommandParser
from arbitrage_bot.telegram.handlers import TelegramHandlers
from arbitrage_bot.telegram.security import AuthorizationGate, ConfirmationManager
from arbitrage_bot.telegram.rate_limit import RateLimiter
from arbitrage_bot.telegram.notifier import Notifier, LogChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramControlledArbitrageBot:
    """
    Main bot class that integrates Telegram interface with arbitrage logic.
    """
    
    def __init__(
        self,
        telegram_config_path: str = "telegram_config.json",
        telegram_token: Optional[str] = None,
        state_getter: Optional[Callable] = None,
    ):
        """
        Initialize the bot.
        
        Args:
            telegram_config_path: Path to telegram_config.json
            telegram_token: Telegram bot token (from env or args)
            state_getter: Callable() -> BotSnapshot for current state
        """
        self.telegram_config_path = telegram_config_path
        self.state_getter = state_getter
        
        # Load config
        telegram_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.config = self._load_config(telegram_config_path, telegram_token)
        
        # Initialize core components
        self.control_queue = ControlQueue(max_size=1000)
        self.bot_loop = BotLoop(
            self.control_queue,
            state_callbacks=self._get_state_callbacks(),
        )
        
        # Initialize Telegram components
        self.auth_gate = AuthorizationGate(self.config.authorized_users)
        self.rate_limiter = RateLimiter()
        self.confirmation_manager = ConfirmationManager()
        
        # Initialize notifier
        self.notifier = Notifier(
            settings=self.config.notification_settings,
            channels=[LogChannel()],  # Replace with TelegramChannel when integrated
        )
        
        # Initialize handlers and router
        self.handlers = TelegramHandlers(
            control_queue=self.control_queue,
            auth_gate=self.auth_gate,
            rate_limiter=self.rate_limiter,
            confirmation_manager=self.confirmation_manager,
            state_getter=self.state_getter,
        )
        
        self.router = self._setup_router()
    
    def _load_config(self, config_path: str, token: Optional[str] = None) -> TelegramConfig:
        """Load Telegram configuration."""
        config = TelegramConfigLoader.load_from_file(config_path, token=token)
        
        if not config:
            logger.warning(f"Could not load config from {config_path}, using defaults")
            config = TelegramConfig(
                enabled=False,
                token=token or "",
                authorized_users=[],
            )
        
        # Validate
        is_valid, error = config.validate()
        if not is_valid and config.enabled:
            logger.error(f"Invalid Telegram config: {error}")
            config.enabled = False
        
        return config
    
    def _setup_router(self) -> CommandRouter:
        """Setup command router with all handlers."""
        router = CommandRouter()
        
        # System/Control commands
        router.register(
            "start", 
            lambda cmd: self.handlers.handle_start(cmd, "user_id_from_message"),
            "Start bot loop"
        )
        router.register(
            "pause",
            lambda cmd: self.handlers.handle_pause(cmd, "user_id_from_message"),
            "Pause new trades (keep risk mgmt)"
        )
        router.register(
            "stop",
            lambda cmd: self.handlers.handle_stop(cmd, "user_id_from_message"),
            "Stop bot loop"
        )
        router.register(
            "mode",
            lambda cmd: self.handlers.handle_mode(cmd, "user_id_from_message"),
            "Change mode: /mode <scan-only|paper|live>"
        )
        router.register(
            "reload_config",
            lambda cmd: self.handlers.handle_reload_config(cmd, "user_id_from_message"),
            "Reload config from disk"
        )
        router.register(
            "help",
            lambda cmd: self.handlers.handle_help(cmd, "user_id_from_message"),
            "Show command help"
        )
        
        # Status/Monitoring commands
        router.register(
            "status",
            lambda cmd: self.handlers.handle_status(cmd, "user_id_from_message"),
            "Show bot status or /status table"
        )
        router.register(
            "balance",
            lambda cmd: self.handlers.handle_balance(cmd, "user_id_from_message"),
            "Show USDC balance"
        )
        router.register(
            "positions",
            lambda cmd: self.handlers.handle_positions(cmd, "user_id_from_message"),
            "Show open positions"
        )
        router.register(
            "orders",
            lambda cmd: self.handlers.handle_orders(cmd, "user_id_from_message"),
            "Show outstanding orders"
        )
        router.register(
            "profit",
            lambda cmd: self.handlers.handle_profit(cmd, "user_id_from_message"),
            "Show PnL summary"
        )
        router.register(
            "daily",
            lambda cmd: self.handlers.handle_daily(cmd, "user_id_from_message"),
            "Daily PnL"
        )
        router.register(
            "weekly",
            lambda cmd: self.handlers.handle_weekly(cmd, "user_id_from_message"),
            "Weekly PnL"
        )
        router.register(
            "monthly",
            lambda cmd: self.handlers.handle_monthly(cmd, "user_id_from_message"),
            "Monthly PnL"
        )
        router.register(
            "performance",
            lambda cmd: self.handlers.handle_performance(cmd, "user_id_from_message"),
            "Show performance stats"
        )
        router.register(
            "risk",
            lambda cmd: self.handlers.handle_risk(cmd, "user_id_from_message"),
            "Show risk limits"
        )
        router.register(
            "show_config",
            lambda cmd: self.handlers.handle_show_config(cmd, "user_id_from_message"),
            "Show sanitized config"
        )
        
        # Action commands
        router.register(
            "freeze",
            lambda cmd: self.handlers.handle_freeze(cmd, "user_id_from_message"),
            "Freeze trading: /freeze <event|venue|all>"
        )
        router.register(
            "unfreeze",
            lambda cmd: self.handlers.handle_unfreeze(cmd, "user_id_from_message"),
            "Unfreeze trading"
        )
        router.register(
            "forceclose",
            lambda cmd: self.handlers.handle_forceclose(cmd, "user_id_from_message"),
            "Force close position(s) (needs confirmation)"
        )
        router.register(
            "cancel",
            lambda cmd: self.handlers.handle_cancel(cmd, "user_id_from_message"),
            "Cancel order(s)"
        )
        router.register(
            "set_limit",
            lambda cmd: self.handlers.handle_set_limit(cmd, "user_id_from_message"),
            "Set risk limit: /set_limit <name> <value>"
        )
        router.register(
            "simulate",
            lambda cmd: self.handlers.handle_simulate(cmd, "user_id_from_message"),
            "Toggle simulation: /simulate <on|off>"
        )
        
        # Debug commands
        router.register(
            "opps",
            lambda cmd: self.handlers.handle_opps(cmd, "user_id_from_message"),
            "Show recent opportunities"
        )
        router.register(
            "why",
            lambda cmd: self.handlers.handle_why(cmd, "user_id_from_message"),
            "Show decision trace"
        )
        router.register(
            "markets",
            lambda cmd: self.handlers.handle_markets(cmd, "user_id_from_message"),
            "List monitored markets"
        )
        router.register(
            "health",
            lambda cmd: self.handlers.handle_health(cmd, "user_id_from_message"),
            "System health check"
        )
        router.register(
            "tg_info",
            lambda cmd: self.handlers.handle_tg_info(cmd, "user_id_from_message"),
            "Show Telegram chat info"
        )
        
        # Confirmation
        router.register(
            "confirm",
            lambda cmd: self.handlers.handle_confirm(cmd, "user_id_from_message"),
            "Confirm action: /confirm <code>"
        )
        
        return router
    
    def _get_state_callbacks(self) -> dict:
        """Get state callbacks for bot loop."""
        return {
            "on_start": self._on_bot_start,
            "on_stop": self._on_bot_stop,
            "on_pause": self._on_bot_pause,
            "on_resume": self._on_bot_resume,
            "on_mode_change": self._on_mode_change,
            "on_freeze": self._on_freeze,
            "on_unfreeze": self._on_unfreeze,
        }
    
    async def _on_bot_start(self, data):
        """Callback when bot starts."""
        logger.info("Bot started via Telegram")
        await self.notifier.notify_startup(self.bot_loop.operating_mode.value)
    
    async def _on_bot_stop(self, data):
        """Callback when bot stops."""
        logger.info("Bot stopped via Telegram")
        await self.notifier.notify_shutdown()
    
    async def _on_bot_pause(self, data):
        """Callback when bot pauses."""
        logger.info("Bot paused via Telegram")
        await self.notifier.notify_warning("Bot paused - no new trades")
    
    async def _on_bot_resume(self, data):
        """Callback when bot resumes."""
        logger.info("Bot resumed via Telegram")
        await self.notifier.notify_warning("Bot resumed")
    
    async def _on_mode_change(self, data):
        """Callback when mode changes."""
        mode = data.get("mode")
        logger.info(f"Mode changed to {mode} via Telegram")
        await self.notifier.notify_warning(f"Operating mode changed to {mode}")
    
    async def _on_freeze(self, data):
        """Callback when freeze is applied."""
        scope = data.get("scope")
        target = data.get("target")
        logger.info(f"Freeze applied: {scope} {target}")
    
    async def _on_unfreeze(self, data):
        """Callback when freeze is removed."""
        scope = data.get("scope")
        target = data.get("target")
        logger.info(f"Unfreeze applied: {scope} {target}")
    
    async def process_message(self, text: str, user_id: str) -> str:
        """
        Process an incoming Telegram message.
        
        Args:
            text: Message text from user
            user_id: Telegram user ID
            
        Returns:
            Response message to send back to user
        """
        # Parse command
        parsed = CommandParser.parse(text)
        if not parsed:
            return "❌ Not a command. Use /help for available commands."
        
        # Check rate limit
        is_allowed, reason = self.rate_limiter.is_allowed(parsed.command, user_id)
        if not is_allowed:
            return reason or "⏱️ Rate limit exceeded."
        
        # Route to handler
        response = await self.router.route(parsed)
        return response
    
    async def start(self):
        """Start the bot loop."""
        logger.info("Starting arbitrage bot with Telegram interface")
        await self.bot_loop.start()
    
    async def stop(self):
        """Stop the bot loop."""
        logger.info("Stopping arbitrage bot")
        await self.bot_loop.stop()


# ==================== EXAMPLE USAGE ====================

async def main():
    """
    Example main function showing how to use the bot.
    """
    # For testing, use a mock state getter
    def mock_state_getter():
        from arbitrage_bot.core.state import BotSnapshot, BotState, OperatingMode
        from datetime import datetime
        return BotSnapshot(
            timestamp=datetime.utcnow(),
            bot_state=BotState.RUNNING,
            operating_mode=OperatingMode.PAPER,
            usdc_available=10000.0,
            usdc_reserved=5000.0,
        )
    
    # Initialize bot
    bot = TelegramControlledArbitrageBot(
        telegram_config_path="telegram_config.json",
        state_getter=mock_state_getter,
    )
    
    # Simulate incoming messages
    test_messages = [
        "/status",
        "/balance",
        "/start",
        "/mode paper",
        "/help",
    ]
    
    for msg in test_messages:
        print(f"\n>>> {msg}")
        response = await bot.process_message(msg, user_id="user1")
        print(f"<<< {response[:100]}...")


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
