"""
Main bot loop that consumes actions from ControlQueue and updates state.

This module defines the interface and basic implementation. It should be
integrated with the actual arbitrage bot logic from the main codebase.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any

from .state import BotState, OperatingMode, BotSnapshot, RiskLimits
from .control_queue import ControlQueue
from .actions import Action, ActionType

logger = logging.getLogger(__name__)


class BotLoop:
    """
    Main async loop for the arbitrage bot.
    
    Consumes actions from ControlQueue and applies state transitions.
    """
    
    def __init__(
        self,
        control_queue: ControlQueue,
        state_callbacks: Optional[Dict[str, Callable]] = None,
        persist_state_path: Optional[str] = None,
    ):
        """
        Initialize the bot loop.
        
        Args:
            control_queue: ControlQueue for receiving commands
            state_callbacks: Dict of callback functions for state changes
            persist_state_path: Path to persist snapshots (JSON)
        """
        self.control_queue = control_queue
        self.persist_state_path = persist_state_path
        
        # State
        self.bot_state = BotState.STOPPED
        self.operating_mode = OperatingMode.SCAN_ONLY
        self.start_time = None
        
        # Callbacks for integrating with real bot
        self.state_callbacks = state_callbacks or {}
        
        # Confirmation tracking
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        
        # Running
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the bot loop (spawns async task)."""
        if self._task:
            logger.warning("Bot loop already running")
            return
        
        self.bot_state = BotState.RUNNING
        self.start_time = datetime.utcnow()
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Bot loop started")
        await self._call_callback("on_start", {})
    
    async def stop(self):
        """Stop the bot loop."""
        self._running = False
        self.bot_state = BotState.STOPPED
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("Bot loop stopped")
        await self._call_callback("on_stop", {})
    
    async def pause(self):
        """Pause the bot (no new trades, but risk management active)."""
        self.bot_state = BotState.PAUSED
        logger.info("Bot paused")
        await self._call_callback("on_pause", {})
    
    async def resume(self):
        """Resume the bot from paused state."""
        self.bot_state = BotState.RUNNING
        logger.info("Bot resumed")
        await self._call_callback("on_resume", {})
    
    async def change_mode(self, mode: str) -> bool:
        """
        Change operating mode.
        
        Args:
            mode: "live", "paper", or "scan-only"
            
        Returns:
            True if successful, False if invalid mode
        """
        try:
            new_mode = OperatingMode(mode)
            self.operating_mode = new_mode
            logger.info(f"Operating mode changed to {mode}")
            await self._call_callback("on_mode_change", {"mode": mode})
            return True
        except ValueError:
            logger.error(f"Invalid mode: {mode}")
            return False
    
    async def _run(self):
        """Main bot loop (internal coroutine)."""
        logger.info("Bot loop running")
        
        while self._running:
            try:
                # Wait for action with timeout
                action = await self.control_queue.dequeue(timeout_sec=1.0)
                
                if action:
                    result = await self._process_action(action)
                    logger.debug(f"Action processed: {action.action_type.value}")
                    await self._call_callback(
                        "on_action_processed",
                        {"action": action.action_type.value, "success": result},
                    )
                else:
                    # No action; do background work (scanning, monitoring, etc.)
                    if self.bot_state == BotState.RUNNING:
                        await self._call_callback("on_scan_cycle", {})
                
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in bot loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)
    
    async def _process_action(self, action: Action) -> bool:
        """
        Process a single action.
        
        Args:
            action: The action to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if action.action_type == ActionType.START_BOT:
                await self.start()
                return True
            
            elif action.action_type == ActionType.PAUSE_BOT:
                await self.pause()
                return True
            
            elif action.action_type == ActionType.STOP_BOT:
                await self.stop()
                return True
            
            elif action.action_type == ActionType.CHANGE_MODE:
                mode = action.metadata.get("mode")
                return await self.change_mode(mode)
            
            elif action.action_type == ActionType.RELOAD_CONFIG:
                await self._call_callback("on_reload_config", {})
                return True
            
            elif action.action_type == ActionType.FREEZE:
                scope = action.metadata.get("scope")
                target = action.metadata.get("target")
                await self._call_callback("on_freeze", {"scope": scope, "target": target})
                return True
            
            elif action.action_type == ActionType.UNFREEZE:
                scope = action.metadata.get("scope")
                target = action.metadata.get("target")
                await self._call_callback("on_unfreeze", {"scope": scope, "target": target})
                return True
            
            elif action.action_type == ActionType.FORCECLOSE_POSITION:
                position_id = action.metadata.get("position_id")
                await self._call_callback("on_forceclose", {"position_id": position_id})
                return True
            
            elif action.action_type == ActionType.CANCEL_ORDER:
                order_id = action.metadata.get("order_id")
                await self._call_callback("on_cancel_order", {"order_id": order_id})
                return True
            
            elif action.action_type == ActionType.SET_RISK_LIMIT:
                limit_name = action.metadata.get("limit_name")
                value = action.metadata.get("value")
                await self._call_callback(
                    "on_set_risk_limit",
                    {"limit_name": limit_name, "value": value}
                )
                return True
            
            elif action.action_type == ActionType.CONFIRM_ACTION:
                request_id = action.metadata.get("request_id")
                code = action.metadata.get("code")
                await self._call_callback(
                    "on_confirm_action",
                    {"request_id": request_id, "code": code}
                )
                return True
            
            else:
                logger.warning(f"Unknown action type: {action.action_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing action: {e}", exc_info=True)
            return False
    
    async def _call_callback(self, callback_name: str, data: dict):
        """
        Call a registered callback if it exists.
        
        Args:
            callback_name: Name of the callback
            data: Data to pass to callback
        """
        if callback_name in self.state_callbacks:
            callback = self.state_callbacks[callback_name]
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in callback {callback_name}: {e}", exc_info=True)
    
    def get_uptime(self) -> float:
        """Get bot uptime in seconds."""
        if not self.start_time:
            return 0.0
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    async def get_snapshot(self) -> BotSnapshot:
        """Get current state snapshot (integrate with real bot to populate all fields)."""
        return BotSnapshot(
            timestamp=datetime.utcnow(),
            bot_state=self.bot_state,
            operating_mode=self.operating_mode,
            usdc_available=0.0,
            usdc_reserved=0.0,
            open_positions=[],
            outstanding_orders=[],
            exposures_by_event={},
            exposures_by_venue={},
            frozen_events=set(),
            frozen_venues=set(),
            frozen_all=False,
            pnl_snapshot=None,
            stats=None,
            risk_limits=RiskLimits(),
        )
    
    def is_running(self) -> bool:
        """Check if bot loop is running."""
        return self._running
    
    def is_paused(self) -> bool:
        """Check if bot is paused."""
        return self.bot_state == BotState.PAUSED
