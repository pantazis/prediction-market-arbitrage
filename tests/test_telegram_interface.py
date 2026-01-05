"""
Comprehensive pytest test suite for the Telegram control interface.

Tests cover:
- Authorization
- Command parsing
- State transitions
- Queue operations
- Notification routing
- Rate limiting
- Configuration
"""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from arbitrage_bot.core.state import (
    BotState, OperatingMode, BotSnapshot, OpenPosition, OutstandingOrder,
    RiskLimits, BotStats, PnLSnapshot
)
from arbitrage_bot.core.actions import Action, ActionType, ControlAction, RiskAction
from arbitrage_bot.core.control_queue import ControlQueue
from arbitrage_bot.core.bot_loop import BotLoop
from arbitrage_bot.config.schema import TelegramConfig, NotificationSettings, NotificationLevel
from arbitrage_bot.telegram.router import CommandParser, ParsedCommand, CommandRouter
from arbitrage_bot.telegram.security import AuthorizationGate, ConfirmationManager, SafeMessageFormatter
from arbitrage_bot.telegram.rate_limit import RateLimiter, CommandRisk
from arbitrage_bot.telegram.notifier import Notifier, LogChannel
from arbitrage_bot.telegram.handlers import TelegramHandlers


# ========== FIXTURES ==========

@pytest.fixture
def control_queue():
    """Create a control queue for testing."""
    return ControlQueue(max_size=100)


@pytest.fixture
def auth_gate():
    """Create authorization gate."""
    return AuthorizationGate(authorized_users=["user1", "user2"])


@pytest.fixture
def rate_limiter():
    """Create rate limiter."""
    return RateLimiter(
        global_rate=100,
        per_user_rate=20,
        high_risk_rate=2,
        medium_risk_rate=5,
    )


@pytest.fixture
def confirmation_manager():
    """Create confirmation manager."""
    return ConfirmationManager(code_length=6, expiry_seconds=300)


@pytest.fixture
def notification_settings():
    """Create notification settings."""
    return NotificationSettings(
        default_level=NotificationLevel.ON,
        startup=NotificationLevel.ON,
        warning=NotificationLevel.ON,
        risk=NotificationLevel.ON,
    )


@pytest.fixture
def notifier(notification_settings):
    """Create notifier with log channel."""
    channel = LogChannel()
    return Notifier(notification_settings, channels=[channel])


@pytest.fixture
def bot_snapshot():
    """Create a sample bot snapshot."""
    return BotSnapshot(
        timestamp=datetime.utcnow(),
        bot_state=BotState.RUNNING,
        operating_mode=OperatingMode.PAPER,
        usdc_available=10000.0,
        usdc_reserved=5000.0,
        open_positions=[
            OpenPosition(
                position_id="pos1",
                event_id="event1",
                outcome_a="YES",
                outcome_b="NO",
                venue_a="polymarket",
                venue_b="omen",
                size=100.0,
                entry_price_a=0.65,
                entry_price_b=0.35,
                entry_time=datetime.utcnow(),
                hedge_status="open",
                unrealized_pnl=50.0,
            )
        ],
        outstanding_orders=[],
        exposures_by_event={"event1": 100.0},
        exposures_by_venue={"polymarket": 65.0, "omen": 35.0},
        frozen_events=set(),
        frozen_venues=set(),
        frozen_all=False,
        pnl_snapshot=PnLSnapshot(
            timestamp=datetime.utcnow(),
            realized_pnl=1000.0,
            unrealized_pnl=500.0,
            fees_paid=50.0,
            slippage_estimate=20.0,
        ),
        stats=BotStats(
            uptime_seconds=3600.0,
            opportunities_found=10,
            opportunities_executed=5,
            opportunities_skipped=5,
        ),
        risk_limits=RiskLimits(),
    )


# ========== COMMAND PARSER TESTS ==========

class TestCommandParser:
    """Test command parsing."""
    
    def test_parse_simple_command(self):
        """Parse simple command without arguments."""
        result = CommandParser.parse("/start")
        assert result is not None
        assert result.command == "start"
        assert result.args == []
    
    def test_parse_command_with_args(self):
        """Parse command with arguments."""
        result = CommandParser.parse("/mode paper")
        assert result is not None
        assert result.command == "mode"
        assert result.args == ["paper"]
    
    def test_parse_command_multiple_args(self):
        """Parse command with multiple arguments."""
        result = CommandParser.parse("/freeze event event123")
        assert result is not None
        assert result.command == "freeze"
        assert result.args == ["event", "event123"]
    
    def test_parse_command_with_quoted_args(self):
        """Parse command with quoted arguments."""
        result = CommandParser.parse('/why "some description"')
        assert result is not None
        assert result.command == "why"
        assert result.args == ["some description"]
    
    def test_parse_invalid_command(self):
        """Non-command text should return None."""
        result = CommandParser.parse("just some text")
        assert result is None
    
    def test_parse_command_case_insensitive(self):
        """Command names should be lowercase."""
        result = CommandParser.parse("/STATUS")
        assert result is not None
        assert result.command == "status"
    
    def test_parsed_command_get_arg(self):
        """Test ParsedCommand.get_arg."""
        cmd = ParsedCommand(
            command="test",
            args=["arg0", "arg1", "arg2"],
            raw_text="/test arg0 arg1 arg2"
        )
        assert cmd.get_arg(0) == "arg0"
        assert cmd.get_arg(1) == "arg1"
        assert cmd.get_arg(5) is None
        assert cmd.get_arg(5, "default") == "default"
    
    def test_parsed_command_get_arg_int(self):
        """Test ParsedCommand.get_arg_int."""
        cmd = ParsedCommand(
            command="positions",
            args=["10"],
            raw_text="/positions 10"
        )
        assert cmd.get_arg_int(0) == 10
        assert cmd.get_arg_int(1, 5) == 5
    
    def test_parsed_command_get_arg_float(self):
        """Test ParsedCommand.get_arg_float."""
        cmd = ParsedCommand(
            command="set_limit",
            args=["max_inventory", "50000.50"],
            raw_text="/set_limit max_inventory 50000.50"
        )
        assert cmd.get_arg_float(1) == 50000.50


# ========== AUTHORIZATION TESTS ==========

class TestAuthorizationGate:
    """Test authorization checks."""
    
    def test_authorized_user(self, auth_gate):
        """Authorized user should pass."""
        assert auth_gate.is_authorized("user1") is True
        assert auth_gate.is_authorized("user2") is True
    
    def test_unauthorized_user(self, auth_gate):
        """Unauthorized user should fail."""
        assert auth_gate.is_authorized("user3") is False
        assert auth_gate.is_authorized("unknown") is False
    
    def test_empty_authorized_list(self):
        """Empty list means no one is authorized."""
        gate = AuthorizationGate([])
        assert gate.is_authorized("user1") is False
    
    def test_can_read_status(self, auth_gate):
        """Anyone can read status (read-only mode)."""
        assert auth_gate.can_read_status("user1") is True
        assert auth_gate.can_read_status("user3") is True
        assert auth_gate.can_read_status("anyone") is True
    
    def test_can_execute_action(self, auth_gate):
        """Only authorized users can execute actions."""
        assert auth_gate.can_execute_action("user1") is True
        assert auth_gate.can_execute_action("user3") is False
    
    def test_deny_message(self, auth_gate):
        """Get denial message."""
        msg = auth_gate.deny_message()
        assert "Unauthorized" in msg


# ========== CONFIRMATION TESTS ==========

class TestConfirmationManager:
    """Test 2-step confirmation flow."""
    
    def test_create_confirmation(self, confirmation_manager):
        """Create a confirmation code."""
        request_id, code = confirmation_manager.create_confirmation(
            "user1", "forceclose all"
        )
        assert request_id is not None
        assert code is not None
        assert len(code) == 6
        assert code.isdigit()
    
    def test_verify_correct_code(self, confirmation_manager):
        """Verify correct confirmation code."""
        request_id, code = confirmation_manager.create_confirmation("user1", "forceclose all")
        
        is_valid, msg = confirmation_manager.verify_confirmation(request_id, "user1", code)
        assert is_valid is True
    
    def test_verify_wrong_code(self, confirmation_manager):
        """Verify with wrong code should fail."""
        request_id, code = confirmation_manager.create_confirmation("user1", "forceclose all")
        
        is_valid, msg = confirmation_manager.verify_confirmation(request_id, "user1", "000000")
        assert is_valid is False
    
    def test_verify_wrong_user(self, confirmation_manager):
        """Verify with wrong user should fail."""
        request_id, code = confirmation_manager.create_confirmation("user1", "forceclose all")
        
        is_valid, msg = confirmation_manager.verify_confirmation(request_id, "user2", code)
        assert is_valid is False
    
    def test_confirmation_expires(self, confirmation_manager):
        """Confirmation should expire."""
        confirmation_manager.expiry_seconds = 0  # Immediate expiry
        request_id, code = confirmation_manager.create_confirmation("user1", "forceclose all")
        
        # Manually set expiry to past
        confirmation_manager.pending[request_id]["expiry"] = datetime.utcnow()
        
        is_valid, msg = confirmation_manager.verify_confirmation(request_id, "user1", code)
        assert is_valid is False
    
    def test_confirmation_single_use(self, confirmation_manager):
        """Confirmation should be consumed on use."""
        request_id, code = confirmation_manager.create_confirmation("user1", "forceclose all")
        
        # First use should succeed
        is_valid1, _ = confirmation_manager.verify_confirmation(request_id, "user1", code)
        assert is_valid1 is True
        
        # Second use should fail (already consumed)
        is_valid2, _ = confirmation_manager.verify_confirmation(request_id, "user1", code)
        assert is_valid2 is False


# ========== RATE LIMITING TESTS ==========

class TestRateLimiter:
    """Test rate limiting."""
    
    def test_allow_normal_rate(self, rate_limiter):
        """Normal usage should be allowed."""
        is_allowed, msg = rate_limiter.is_allowed("status", "user1")
        assert is_allowed is True
    
    def test_low_risk_command(self, rate_limiter):
        """Low-risk commands should have no limit."""
        for _ in range(10):
            is_allowed, msg = rate_limiter.is_allowed("status", "user1")
            assert is_allowed is True
    
    def test_high_risk_per_user(self, rate_limiter):
        """High-risk commands should be rate limited per user."""
        # Allow first 2
        is_allowed1, _ = rate_limiter.is_allowed("forceclose", "user1")
        assert is_allowed1 is True
        
        is_allowed2, _ = rate_limiter.is_allowed("forceclose", "user1")
        assert is_allowed2 is True
        
        # Third should fail
        is_allowed3, msg = rate_limiter.is_allowed("forceclose", "user1")
        assert is_allowed3 is False
        assert msg is not None
    
    def test_per_user_isolation(self, rate_limiter):
        """Different users should have separate rate limits."""
        # User1 executes high-risk command twice (at limit)
        rate_limiter.is_allowed("forceclose", "user1")
        rate_limiter.is_allowed("forceclose", "user1")
        
        # User2 should still be able to execute
        is_allowed, _ = rate_limiter.is_allowed("forceclose", "user2")
        assert is_allowed is True
    
    def test_stats(self, rate_limiter):
        """Get rate limiter stats."""
        rate_limiter.is_allowed("status", "user1")
        rate_limiter.is_allowed("status", "user2")
        
        stats = rate_limiter.stats()
        assert "global_history_entries" in stats
        assert "user_history_entries" in stats
        assert "tracked_users" in stats


# ========== CONTROL QUEUE TESTS ==========

@pytest.mark.asyncio
class TestControlQueue:
    """Test control queue operations."""
    
    async def test_enqueue_action(self, control_queue):
        """Enqueue an action."""
        action = ControlAction.start_bot("user1")
        success = await control_queue.enqueue(action)
        assert success is True
        assert control_queue.size() == 1
    
    async def test_dequeue_action(self, control_queue):
        """Dequeue an action."""
        action = ControlAction.start_bot("user1")
        await control_queue.enqueue(action)
        
        dequeued = await control_queue.dequeue(timeout_sec=1.0)
        assert dequeued is not None
        assert dequeued.action_type == ActionType.START_BOT
    
    async def test_queue_fifo(self, control_queue):
        """Queue should be FIFO."""
        action1 = ControlAction.start_bot("user1")
        action2 = ControlAction.pause_bot("user1")
        
        await control_queue.enqueue(action1)
        await control_queue.enqueue(action2)
        
        first = await control_queue.dequeue(timeout_sec=1.0)
        second = await control_queue.dequeue(timeout_sec=1.0)
        
        assert first.action_type == ActionType.START_BOT
        assert second.action_type == ActionType.PAUSE_BOT
    
    async def test_dequeue_timeout(self, control_queue):
        """Dequeue with timeout should return None if empty."""
        result = await control_queue.dequeue(timeout_sec=0.1)
        assert result is None
    
    async def test_queue_stats(self, control_queue):
        """Get queue statistics."""
        action = ControlAction.start_bot("user1")
        await control_queue.enqueue(action)
        
        stats = control_queue.stats()
        assert stats["queue_size"] == 1
        assert stats["max_size"] == 100
        assert stats["processed_count"] == 0


# ========== BOT LOOP TESTS ==========

@pytest.mark.asyncio
class TestBotLoop:
    """Test bot loop state management."""
    
    async def test_start_bot(self, control_queue):
        """Starting bot should change state to RUNNING."""
        loop = BotLoop(control_queue)
        assert loop.bot_state == BotState.STOPPED
        
        await loop.start()
        assert loop.bot_state == BotState.RUNNING
        assert loop.is_running() is True
        
        await loop.stop()
    
    async def test_pause_bot(self, control_queue):
        """Pausing bot should change state to PAUSED."""
        loop = BotLoop(control_queue)
        await loop.start()
        
        await loop.pause()
        assert loop.bot_state == BotState.PAUSED
        assert loop.is_paused() is True
        
        await loop.stop()
    
    async def test_stop_bot(self, control_queue):
        """Stopping bot should change state to STOPPED."""
        loop = BotLoop(control_queue)
        await loop.start()
        
        await loop.stop()
        assert loop.bot_state == BotState.STOPPED
        assert loop.is_running() is False
    
    async def test_change_mode(self, control_queue):
        """Changing mode should update operating_mode."""
        loop = BotLoop(control_queue)
        
        success = await loop.change_mode("paper")
        assert success is True
        assert loop.operating_mode == OperatingMode.PAPER
        
        success = await loop.change_mode("live")
        assert success is True
        assert loop.operating_mode == OperatingMode.LIVE
    
    async def test_change_invalid_mode(self, control_queue):
        """Invalid mode should fail."""
        loop = BotLoop(control_queue)
        
        success = await loop.change_mode("invalid")
        assert success is False
    
    async def test_uptime_calculation(self, control_queue):
        """Uptime should increase."""
        loop = BotLoop(control_queue)
        
        await loop.start()
        await asyncio.sleep(0.1)
        uptime = loop.get_uptime()
        
        assert uptime > 0
        assert uptime < 1.0  # Should be less than 1 second
        
        await loop.stop()
    
    async def test_bot_callbacks(self, control_queue):
        """Callbacks should be called."""
        callback_called = {"start": False}
        
        async def on_start(data):
            callback_called["start"] = True
        
        loop = BotLoop(
            control_queue,
            state_callbacks={"on_start": on_start}
        )
        
        await loop.start()
        await asyncio.sleep(0.1)
        
        assert callback_called["start"] is True
        await loop.stop()


# ========== NOTIFICATION TESTS ==========

@pytest.mark.asyncio
class TestNotifier:
    """Test notification system."""
    
    async def test_notify_when_enabled(self, notifier):
        """Notification should be sent when enabled."""
        result = await notifier.notify("startup", "Test message")
        assert result is True
    
    async def test_notify_when_disabled(self, notification_settings):
        """Notification should be suppressed when disabled."""
        settings = NotificationSettings(
            default_level=NotificationLevel.OFF
        )
        notifier = Notifier(settings, channels=[LogChannel()])
        
        result = await notifier.notify("startup", "Test message")
        assert result is False
    
    async def test_notify_silent_mode(self, notification_settings):
        """Silent mode should suppress notification but not block it."""
        settings = NotificationSettings(
            startup=NotificationLevel.SILENT
        )
        notifier = Notifier(settings, channels=[LogChannel()])
        
        # Should not notify (silent)
        result = await notifier.notify("startup", "Test message")
        assert result is False  # SILENT means don't send
    
    async def test_notify_force(self, notification_settings):
        """Force flag should bypass settings."""
        settings = NotificationSettings(
            startup=NotificationLevel.OFF
        )
        notifier = Notifier(settings, channels=[LogChannel()])
        
        result = await notifier.notify("startup", "Test message", force=True)
        assert result is True
    
    async def test_notifier_stats(self, notifier):
        """Get notifier stats."""
        await notifier.notify("startup", "Message 1")
        await notifier.notify("warning", "Message 2")
        
        stats = notifier.stats()
        assert stats["sent_count"] == 2
        assert stats["channels"] == 1


# ========== CONFIGURATION TESTS ==========

class TestTelegramConfig:
    """Test Telegram configuration."""
    
    def test_config_validate_enabled(self):
        """Enabled config must have token and chat_id."""
        config = TelegramConfig(
            enabled=True,
            token="",
            chat_id="123"
        )
        is_valid, error = config.validate()
        assert is_valid is False
        assert "token" in error.lower()
    
    def test_config_validate_disabled(self):
        """Disabled config doesn't need token."""
        config = TelegramConfig(
            enabled=False,
            token="",
            chat_id=""
        )
        is_valid, error = config.validate()
        assert is_valid is True
    
    def test_config_authorization(self):
        """Test authorization check."""
        config = TelegramConfig(
            authorized_users=["user1", "user2"]
        )
        
        assert config.is_authorized("user1") is True
        assert config.is_authorized("user3") is False
    
    def test_config_to_dict_sanitizes_token(self):
        """Token should be excluded from dict by default."""
        config = TelegramConfig(
            token="secret-token",
            chat_id="123"
        )
        
        data = config.to_dict(include_token=False)
        assert "token" not in data
        
        data_with_token = config.to_dict(include_token=True)
        assert data_with_token["token"] == "secret-token"


# ========== HANDLER TESTS ==========

@pytest.mark.asyncio
class TestTelegramHandlers:
    """Test command handlers."""
    
    def get_handlers(self, auth_gate=None, control_queue=None, state_getter=None):
        """Helper to create handlers."""
        if auth_gate is None:
            auth_gate = AuthorizationGate(["user1"])
        if control_queue is None:
            control_queue = ControlQueue()
        
        return TelegramHandlers(
            control_queue=control_queue,
            auth_gate=auth_gate,
            rate_limiter=RateLimiter(),
            confirmation_manager=ConfirmationManager(),
            state_getter=state_getter,
        )
    
    async def test_start_authorized(self):
        """Authorized user can start bot."""
        handlers = self.get_handlers()
        cmd = ParsedCommand("start", [], "/start")
        
        response = await handlers.handle_start(cmd, "user1")
        assert "✅" in response or "starting" in response.lower()
    
    async def test_start_unauthorized(self):
        """Unauthorized user cannot start bot."""
        auth_gate = AuthorizationGate([])  # No one authorized
        handlers = self.get_handlers(auth_gate=auth_gate)
        cmd = ParsedCommand("start", [], "/start")
        
        response = await handlers.handle_start(cmd, "user1")
        assert "Unauthorized" in response
    
    async def test_status_read_only(self):
        """Anyone can read status."""
        def mock_state_getter():
            return BotSnapshot(
                timestamp=datetime.utcnow(),
                bot_state=BotState.RUNNING,
                operating_mode=OperatingMode.PAPER,
            )
        
        auth_gate = AuthorizationGate([])  # No one authorized
        handlers = self.get_handlers(
            auth_gate=auth_gate,
            state_getter=mock_state_getter
        )
        cmd = ParsedCommand("status", [], "/status")
        
        response = await handlers.handle_status(cmd, "anyone")
        assert response is not None
        assert "RUNNING" in response
    
    async def test_mode_change(self):
        """Change operating mode."""
        handlers = self.get_handlers()
        cmd = ParsedCommand("mode", ["paper"], "/mode paper")
        
        response = await handlers.handle_mode(cmd, "user1")
        assert "paper" in response.lower()
    
    async def test_mode_invalid(self):
        """Invalid mode should error."""
        handlers = self.get_handlers()
        cmd = ParsedCommand("mode", ["invalid"], "/mode invalid")
        
        response = await handlers.handle_mode(cmd, "user1")
        assert "Invalid" in response
    
    async def test_balance_display(self):
        """Display balance."""
        def mock_state_getter():
            snap = BotSnapshot(
                timestamp=datetime.utcnow(),
                bot_state=BotState.RUNNING,
                operating_mode=OperatingMode.PAPER,
                usdc_available=10000.0,
                usdc_reserved=5000.0,
            )
            return snap
        
        handlers = self.get_handlers(state_getter=mock_state_getter)
        cmd = ParsedCommand("balance", [], "/balance")
        
        response = await handlers.handle_balance(cmd, "user1")
        assert "10,000" in response or "10000" in response
        assert "5,000" in response or "5000" in response


# ========== SAFE MESSAGE FORMATTING ==========

class TestSafeMessageFormatter:
    """Test message formatting utilities."""
    
    def test_format_quantity(self):
        """Format quantity nicely."""
        assert SafeMessageFormatter.format_quantity(1000.123) == "1,000.12"
        assert SafeMessageFormatter.format_quantity(50.5, 1) == "50.5"
    
    def test_format_percentage(self):
        """Format percentage nicely."""
        assert SafeMessageFormatter.format_percentage(5.123) == "5.12%"
    
    def test_format_time_delta(self):
        """Format time delta nicely."""
        assert SafeMessageFormatter.format_time_delta(30) == "30s"
        assert SafeMessageFormatter.format_time_delta(120) == "2m 0s"
        assert SafeMessageFormatter.format_time_delta(3661) == "1h 1m"
    
    def test_sanitize_config(self):
        """Config should sanitize secrets."""
        config = {
            "api_key": "secret123",
            "username": "alice",
            "nested": {
                "token": "secret456"
            }
        }
        
        sanitized = SafeMessageFormatter.sanitize_config_for_display(config)
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["username"] == "alice"
        assert sanitized["nested"]["token"] == "***REDACTED***"


# ========== INTEGRATION TESTS ==========

@pytest.mark.asyncio
class TestIntegration:
    """Integration tests combining multiple components."""
    
    async def test_command_flow(self):
        """Test complete command flow."""
        # Setup
        control_queue = ControlQueue()
        auth_gate = AuthorizationGate(["user1"])
        handlers = TelegramHandlers(
            control_queue=control_queue,
            auth_gate=auth_gate,
            rate_limiter=RateLimiter(),
            confirmation_manager=ConfirmationManager(),
        )
        router = CommandRouter()
        
        # Register handler (wrap with user_id)
        user_id = "user1"
        async def wrapped_start(cmd):
            return await handlers.handle_start(cmd, user_id)
        
        router.register("start", wrapped_start)
        
        # Parse and route command
        parsed = CommandParser.parse("/start")
        assert parsed is not None
        
        response = await router.route(parsed)
        assert response is not None
        
        # Check queue
        action = await control_queue.dequeue(timeout_sec=1.0)
        assert action is not None
        assert action.action_type == ActionType.START_BOT
    
    async def test_authorization_enforcement(self):
        """Test authorization is enforced across handlers."""
        control_queue = ControlQueue()
        auth_gate = AuthorizationGate(["user1"])
        handlers = TelegramHandlers(
            control_queue=control_queue,
            auth_gate=auth_gate,
            rate_limiter=RateLimiter(),
            confirmation_manager=ConfirmationManager(),
        )
        
        cmd = ParsedCommand("pause", [], "/pause")
        
        # Authorized user
        response = await handlers.handle_pause(cmd, "user1")
        assert "✅" in response or "paused" in response.lower()
        
        # Unauthorized user
        response = await handlers.handle_pause(cmd, "user2")
        assert "Unauthorized" in response
    
    async def test_confirmation_flow(self):
        """Test 2-step confirmation flow."""
        control_queue = ControlQueue()
        auth_gate = AuthorizationGate(["user1"])
        confirmation_manager = ConfirmationManager()
        
        handlers = TelegramHandlers(
            control_queue=control_queue,
            auth_gate=auth_gate,
            rate_limiter=RateLimiter(),
            confirmation_manager=confirmation_manager,
        )
        
        user_id = "user1"
        
        # Step 1: Request forceclose
        cmd = ParsedCommand("forceclose", ["all"], "/forceclose all")
        response1 = await handlers.handle_forceclose(cmd, user_id)
        
        assert "CONFIRMATION REQUIRED" in response1
        assert "confirm" in response1.lower()
        
        # Get pending confirmations manually 
        assert len(confirmation_manager.pending) > 0
        
        # Extract code from confirmation manager's pending dict
        request_id, confirmation_data = list(confirmation_manager.pending.items())[0]
        code = confirmation_data["code"]
        
        # Step 2: Confirm
        cmd_confirm = ParsedCommand("confirm", [code], f"/confirm {code}")
        response2 = await handlers.handle_confirm(cmd_confirm, user_id)
        
        assert "✅" in response2 or "confirmed" in response2.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
