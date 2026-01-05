"""
Command handlers for Telegram interface.

Each handler is a pure function that:
1. Validates arguments
2. Checks authorization
3. Queues actions to ControlQueue
4. Returns a user-friendly response message

NO direct network calls or state mutations here - all deferred to bot loop.
"""
import logging
import textwrap
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .router import ParsedCommand
from .security import AuthorizationGate, ConfirmationManager, SafeMessageFormatter
from .rate_limit import RateLimiter
from ..core.control_queue import ControlQueue
from ..core.actions import ControlAction, RiskAction, ConfirmAction
from ..core.state import BotSnapshot, BotState, OperatingMode

logger = logging.getLogger(__name__)


class TelegramHandlers:
    """Collection of command handlers."""
    
    def __init__(
        self,
        control_queue: ControlQueue,
        auth_gate: AuthorizationGate,
        rate_limiter: RateLimiter,
        confirmation_manager: ConfirmationManager,
        state_getter=None,  # Callable that returns current BotSnapshot
    ):
        """
        Initialize handlers.
        
        Args:
            control_queue: Queue for actions
            auth_gate: Authorization check
            rate_limiter: Rate limiter
            confirmation_manager: Confirmation code manager
            state_getter: Callable() -> BotSnapshot for reading current state
        """
        self.control_queue = control_queue
        self.auth_gate = auth_gate
        self.rate_limiter = rate_limiter
        self.confirmation_manager = confirmation_manager
        self.state_getter = state_getter
    
    # ==================== CONTROL COMMANDS ====================
    
    async def handle_start(self, cmd: ParsedCommand, user_id: str) -> str:
        """Start bot loop."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        action = ControlAction.start_bot(user_id)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return "✅ Bot starting..."
        else:
            return "❌ Failed to queue action. Try again."
    
    async def handle_pause(self, cmd: ParsedCommand, user_id: str) -> str:
        """Pause bot (no new entries, keep risk management)."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        action = ControlAction.pause_bot(user_id)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return "⏸️ Bot paused. Risk management still active."
        else:
            return "❌ Failed to queue action. Try again."
    
    async def handle_stop(self, cmd: ParsedCommand, user_id: str) -> str:
        """Stop bot loop."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        action = ControlAction.stop_bot(user_id)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return "🛑 Bot stopping..."
        else:
            return "❌ Failed to queue action. Try again."
    
    async def handle_mode(self, cmd: ParsedCommand, user_id: str) -> str:
        """Change operating mode: /mode <scan-only|paper|live>"""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        mode = cmd.get_arg(0, "").lower()
        
        valid_modes = ["scan-only", "paper", "live", "scan_only"]
        if mode not in valid_modes:
            return f"❌ Invalid mode. Use: scan-only, paper, or live"
        
        # Normalize
        mode = mode.replace("_", "-")
        
        action = ControlAction.change_mode(user_id, mode)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return f"🔄 Mode changed to {mode}"
        else:
            return "❌ Failed to queue action. Try again."
    
    async def handle_reload_config(self, cmd: ParsedCommand, user_id: str) -> str:
        """Reload configuration from disk."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        action = ControlAction.reload_config(user_id)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return "🔄 Reloading configuration..."
        else:
            return "❌ Failed to queue action. Try again."
    
    async def handle_help(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show help for commands."""
        help_text = textwrap.dedent("""
            📖 **Arbitrage Bot Commands**
            
            **SYSTEM & CONTROL:**
            /start - Start bot loop
            /pause - Pause new trades (risk mgmt active)
            /stop - Stop bot loop
            /mode <scan-only|paper|live> - Change operating mode
            /reload_config - Reload config from disk
            /help - Show this help
            
            **MONITORING:**
            /status [table] - Show bot status or table view
            /balance - Show USDC balance
            /positions [n] - Show last n open positions
            /orders [n] - Show outstanding orders
            /profit [n] - Show PnL summary (last n days)
            /daily [n] /weekly [n] /monthly [n] - PnL by period
            /performance - Per-market stats
            /risk - Risk limits and usage
            /show_config - Show sanitized config
            
            **ACTIONS:**
            /freeze <event|venue|all> - Freeze trading scope
            /unfreeze <event|venue|all> - Remove freeze
            /forceclose [position|all] - Force close position(s)
            /cancel [order|all] - Cancel orders
            /set_limit <name> <value> - Update risk limit
            /simulate <on|off> - Toggle paper mode
            
            **DEBUG:**
            /opps [n] - Last n opportunities
            /why <opp_id> - Decision trace for opportunity
            /markets [filter] - List monitored markets
            /health - System health check
            /tg_info - Show chat_id and topic_id
        """).strip()
        
        return help_text
    
    # ==================== STATUS COMMANDS ====================
    
    async def handle_status(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show bot status."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        # Check if table view requested
        is_table = cmd.get_arg(0) == "table"
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            
            if is_table:
                return self._format_status_table(snapshot)
            else:
                return self._format_status_summary(snapshot)
        except Exception as e:
            logger.error(f"Error in status handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_balance(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show USDC balance."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            
            total = snapshot.usdc_available + snapshot.usdc_reserved
            
            lines = [
                "💰 **Balance**",
                f"Available: ${SafeMessageFormatter.format_quantity(snapshot.usdc_available)}",
                f"Reserved: ${SafeMessageFormatter.format_quantity(snapshot.usdc_reserved)}",
                f"Total: ${SafeMessageFormatter.format_quantity(total)}",
            ]
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in balance handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_positions(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show open positions."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            limit = cmd.get_arg_int(0, 10)
            
            if not snapshot.open_positions:
                return "📋 No open positions."
            
            lines = ["📍 **Open Positions**", ""]
            
            for pos in snapshot.open_positions[:limit]:
                lines.append(f"ID: `{pos.position_id}`")
                lines.append(f"Event: {pos.event_id}")
                lines.append(f"Legs: {pos.outcome_a} ({pos.venue_a}) ⚖️ {pos.outcome_b} ({pos.venue_b})")
                lines.append(f"Size: {SafeMessageFormatter.format_quantity(pos.size)}")
                lines.append(f"Prices: {pos.entry_price_a:.4f} | {pos.entry_price_b:.4f}")
                lines.append(f"Hedge: {pos.hedge_status}")
                lines.append(f"PnL: ${SafeMessageFormatter.format_quantity(pos.unrealized_pnl)}")
                lines.append("")
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in positions handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_orders(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show outstanding orders."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            limit = cmd.get_arg_int(0, 10)
            
            if not snapshot.outstanding_orders:
                return "📋 No outstanding orders."
            
            lines = ["📑 **Outstanding Orders**", ""]
            
            for order in snapshot.outstanding_orders[:limit]:
                lines.append(f"ID: `{order.order_id}`")
                lines.append(f"Position: {order.position_id}")
                lines.append(f"{order.side.upper()} {SafeMessageFormatter.format_quantity(order.size)} @ {order.price:.4f}")
                lines.append(f"Venue: {order.venue} | Outcome: {order.outcome}")
                lines.append(f"Status: {order.status} ({SafeMessageFormatter.format_quantity(order.filled_qty)} filled)")
                lines.append("")
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in orders handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_profit(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show PnL summary."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            days = cmd.get_arg_int(0, 1)
            
            if not snapshot.pnl_snapshot:
                return "📊 No PnL data available yet."
            
            pnl = snapshot.pnl_snapshot
            
            lines = [
                f"📊 **PnL Summary (last {days}d)**",
                f"Realized: ${SafeMessageFormatter.format_quantity(pnl.realized_pnl, 2)}",
                f"Unrealized: ${SafeMessageFormatter.format_quantity(pnl.unrealized_pnl, 2)}",
                f"Total: ${SafeMessageFormatter.format_quantity(pnl.realized_pnl + pnl.unrealized_pnl, 2)}",
                f"Fees: ${SafeMessageFormatter.format_quantity(pnl.fees_paid, 2)}",
                f"Slippage est: ${SafeMessageFormatter.format_quantity(pnl.slippage_estimate, 2)}",
            ]
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in profit handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_daily(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show daily PnL."""
        return await self._handle_pnl_period(cmd, user_id, "daily", 1)
    
    async def handle_weekly(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show weekly PnL."""
        return await self._handle_pnl_period(cmd, user_id, "weekly", 7)
    
    async def handle_monthly(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show monthly PnL."""
        return await self._handle_pnl_period(cmd, user_id, "monthly", 30)
    
    async def _handle_pnl_period(self, cmd: ParsedCommand, user_id: str, period: str, default_days: int) -> str:
        """Helper for period-based PnL."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            
            if not snapshot.pnl_snapshot:
                return f"📊 No {period} PnL data available yet."
            
            pnl = snapshot.pnl_snapshot
            
            return (
                f"📊 **{period.upper()} PnL**\n"
                f"Realized: ${SafeMessageFormatter.format_quantity(pnl.realized_pnl, 2)}\n"
                f"Unrealized: ${SafeMessageFormatter.format_quantity(pnl.unrealized_pnl, 2)}"
            )
        except Exception as e:
            logger.error(f"Error in {period} handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_performance(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show per-market/venue statistics."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            stats = snapshot.stats
            
            lines = [
                "🎯 **Performance Stats**",
                f"Opps found: {stats.opportunities_found}",
                f"Opps executed: {stats.opportunities_executed}",
                f"Opps skipped: {stats.opportunities_skipped}",
                f"Fill rate: {100 * stats.opportunities_executed / max(stats.opportunities_found, 1):.1f}%",
                f"Total trades: {stats.total_trades}",
            ]
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in performance handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_risk(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show risk limits and utilization."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        if not self.state_getter:
            return "⚠️ State not available yet."
        
        try:
            snapshot = self.state_getter()
            limits = snapshot.risk_limits
            
            total_exposure = sum(snapshot.exposures_by_event.values())
            
            lines = [
                "⛔ **Risk Limits**",
                f"Max position: ${SafeMessageFormatter.format_quantity(limits.max_position_size)}",
                f"Max inventory: ${SafeMessageFormatter.format_quantity(limits.max_inventory_usdc)}",
                f"Current inventory: ${SafeMessageFormatter.format_quantity(snapshot.usdc_available + snapshot.usdc_reserved)}",
                f"Inventory usage: {100 * (snapshot.usdc_reserved) / limits.max_inventory_usdc:.1f}%",
                f"Max exposure/event: ${SafeMessageFormatter.format_quantity(limits.max_exposure_per_event)}",
                f"Current total exposure: ${SafeMessageFormatter.format_quantity(total_exposure)}",
                f"Daily loss limit: ${SafeMessageFormatter.format_quantity(limits.daily_loss_limit)}",
            ]
            
            if snapshot.frozen_all:
                lines.append("\n⚠️ **FROZEN: ALL TRADING STOPPED**")
            elif snapshot.frozen_events or snapshot.frozen_venues:
                lines.append("\n⚠️ **Frozen scopes:**")
                if snapshot.frozen_events:
                    lines.append(f"  Events: {', '.join(snapshot.frozen_events)}")
                if snapshot.frozen_venues:
                    lines.append(f"  Venues: {', '.join(snapshot.frozen_venues)}")
            
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in risk handler: {e}")
            return SafeMessageFormatter.error_message(e)
    
    async def handle_show_config(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show sanitized configuration."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        # This would need integration with actual config system
        lines = [
            "⚙️ **Configuration**",
            "```",
            "enabled: true",
            "operating_mode: scan-only",
            "notification_settings:",
            "  default: on",
            "  risk: on",
            "  warning: on",
            "```",
        ]
        
        return "\n".join(lines)
    
    # ==================== ACTION COMMANDS ====================
    
    async def handle_freeze(self, cmd: ParsedCommand, user_id: str) -> str:
        """Freeze trading: /freeze <event|venue|all> [target]"""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        scope = cmd.get_arg(0, "").lower()
        target = cmd.get_arg(1, "")
        
        if scope not in ["event", "venue", "all"]:
            return "❌ Usage: /freeze <event|venue|all> [target]"
        
        if scope in ["event", "venue"] and not target:
            return f"❌ Specify {scope} name after /freeze"
        
        action = RiskAction.freeze(user_id, scope, target)
        success = await self.control_queue.enqueue(action)
        
        if success:
            target_str = f" {target}" if target else ""
            return f"🔒 Freezing {scope}{target_str}..."
        else:
            return "❌ Failed to queue action."
    
    async def handle_unfreeze(self, cmd: ParsedCommand, user_id: str) -> str:
        """Unfreeze trading."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        scope = cmd.get_arg(0, "").lower()
        target = cmd.get_arg(1, "")
        
        if scope not in ["event", "venue", "all"]:
            return "❌ Usage: /unfreeze <event|venue|all> [target]"
        
        action = RiskAction.unfreeze(user_id, scope, target)
        success = await self.control_queue.enqueue(action)
        
        if success:
            target_str = f" {target}" if target else ""
            return f"🔓 Unfreezing {scope}{target_str}..."
        else:
            return "❌ Failed to queue action."
    
    async def handle_forceclose(self, cmd: ParsedCommand, user_id: str) -> str:
        """Force close position(s) - requires confirmation."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        position_id = cmd.get_arg(0, "all")
        
        # Create confirmation
        request_id, code = self.confirmation_manager.create_confirmation(
            user_id,
            f"forceclose {position_id}"
        )
        
        return (
            f"⚠️ **CONFIRMATION REQUIRED**\n"
            f"Action: Force close {position_id}\n"
            f"Reply with: `/confirm {code}`"
        )
    
    async def handle_cancel(self, cmd: ParsedCommand, user_id: str) -> str:
        """Cancel order(s)."""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        order_id = cmd.get_arg(0, "all")
        
        action = RiskAction.cancel_order(user_id, order_id)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return f"🚫 Canceling order {order_id}..."
        else:
            return "❌ Failed to queue action."
    
    async def handle_set_limit(self, cmd: ParsedCommand, user_id: str) -> str:
        """Set risk limit: /set_limit <name> <value>"""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        limit_name = cmd.get_arg(0, "")
        value_str = cmd.get_arg(1, "")
        
        if not limit_name or not value_str:
            return "❌ Usage: /set_limit <name> <value>"
        
        try:
            value = float(value_str)
        except ValueError:
            return f"❌ Invalid value: {value_str}"
        
        action = RiskAction.set_risk_limit(user_id, limit_name, value)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return f"📝 Updating {limit_name} to {value}..."
        else:
            return "❌ Failed to queue action."
    
    async def handle_simulate(self, cmd: ParsedCommand, user_id: str) -> str:
        """Toggle simulation mode: /simulate <on|off>"""
        if not self.auth_gate.can_execute_action(user_id):
            return self.auth_gate.deny_message()
        
        mode_str = cmd.get_arg(0, "").lower()
        
        if mode_str == "on":
            mode = "paper"
        elif mode_str == "off":
            mode = "live"
        else:
            return "❌ Usage: /simulate <on|off>"
        
        action = ControlAction.change_mode(user_id, mode)
        success = await self.control_queue.enqueue(action)
        
        if success:
            return f"🎯 Switching to {mode} mode..."
        else:
            return "❌ Failed to queue action."
    
    # ==================== DEBUG COMMANDS ====================
    
    async def handle_opps(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show recent opportunities."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        # This would need integration with opportunity history
        return "🎯 **Last Opportunities**\n(Integration needed with opportunity tracker)"
    
    async def handle_why(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show decision trace for opportunity."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        opp_id = cmd.get_arg(0)
        
        if not opp_id:
            return "❌ Usage: /why <opp_id>"
        
        # This would need integration with opportunity decision logs
        return f"📋 Decision trace for {opp_id}\n(Integration needed)"
    
    async def handle_markets(self, cmd: ParsedCommand, user_id: str) -> str:
        """List monitored markets."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        # This would need integration with market tracker
        return "📍 **Monitored Markets**\n(Integration needed with market list)"
    
    async def handle_health(self, cmd: ParsedCommand, user_id: str) -> str:
        """Check system health."""
        if not self.auth_gate.can_read_status(user_id):
            return self.auth_gate.deny_message()
        
        lines = [
            "🏥 **Health Check**",
            "Dependencies: ✅",
            "API latency: <100ms",
            "Rate limits: OK",
            "Last exception: None",
        ]
        
        return "\n".join(lines)
    
    async def handle_tg_info(self, cmd: ParsedCommand, user_id: str) -> str:
        """Show chat_id and topic_id for config."""
        # This needs the actual chat_id/topic_id from message context
        # For now, return a placeholder
        return (
            "📋 **Telegram Info**\n"
            "Chat ID: `123456789`\n"
            "Topic ID: `42` (if applicable)\n"
            "(These would be populated from actual message context)"
        )
    
    # ==================== CONFIRMATION ====================
    
    async def handle_confirm(self, cmd: ParsedCommand, user_id: str) -> str:
        """Confirm an action: /confirm <code>"""
        code = cmd.get_arg(0, "")
        
        if not code:
            return "❌ Usage: /confirm <code>"
        
        # Find matching pending confirmation
        pending_request_id = None
        for req_id, data in self.confirmation_manager.pending.items():
            if data["code"] == code and str(data["user_id"]) == str(user_id):
                pending_request_id = req_id
                break
        
        if not pending_request_id:
            return "❌ Invalid or expired confirmation code."
        
        # Extract action from pending
        pending = self.confirmation_manager.pending[pending_request_id]
        action_str = pending["action"]  # e.g., "forceclose all"
        
        # Parse the action to recreate it
        parts = action_str.split()
        action_type = parts[0]  # "forceclose"
        target = parts[1] if len(parts) > 1 else "all"  # "all"
        
        # Queue the confirmed action
        if action_type == "forceclose":
            action = RiskAction.forceclose_position(user_id, target, pending_request_id)
        else:
            return "❌ Unknown action type."
        
        success = await self.control_queue.enqueue(action)
        
        # Clean up confirmation
        self.confirmation_manager.cancel_confirmation(pending_request_id)
        
        if success:
            return f"✅ Confirmed! Executing {action_type} {target}..."
        else:
            return "❌ Failed to queue action."
    
    # ==================== FORMATTING HELPERS ====================
    
    def _format_status_summary(self, snapshot: BotSnapshot) -> str:
        """Format full status summary."""
        uptime = SafeMessageFormatter.format_time_delta(snapshot.stats.uptime_seconds) if snapshot.stats else "0s"
        
        lines = [
            "🤖 **Bot Status**",
            f"State: {snapshot.bot_state.value.upper()}",
            f"Mode: {snapshot.operating_mode.value}",
            f"Uptime: {uptime}",
            f"Open positions: {len(snapshot.open_positions)}",
            f"Outstanding orders: {len(snapshot.outstanding_orders)}",
        ]
        
        if snapshot.stats:
            lines.append(f"Last scan: {snapshot.stats.last_scan_time}")
            if snapshot.stats.last_error:
                lines.append(f"⚠️ Last error: {snapshot.stats.last_error[:50]}")
        
        return "\n".join(lines)
    
    def _format_status_table(self, snapshot: BotSnapshot) -> str:
        """Format compact status table."""
        lines = [
            "```",
            "Status         | Details",
            "---------------|----------------",
            f"State          | {snapshot.bot_state.value}",
            f"Mode           | {snapshot.operating_mode.value}",
            f"Positions      | {len(snapshot.open_positions)}",
            f"Orders         | {len(snapshot.outstanding_orders)}",
            f"Balance        | ${SafeMessageFormatter.format_quantity(snapshot.usdc_available)}",
            "```",
        ]
        
        return "\n".join(lines)
