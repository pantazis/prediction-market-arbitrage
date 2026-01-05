"""
Action definitions for the arbitrage bot.

Actions are queued by command handlers and consumed by the bot loop.
This separation ensures handlers are pure functions without side effects.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional
from enum import Enum
from datetime import datetime


class ActionType(Enum):
    """Types of actions that can be queued."""
    # Control
    START_BOT = "start_bot"
    PAUSE_BOT = "pause_bot"
    STOP_BOT = "stop_bot"
    CHANGE_MODE = "change_mode"
    RELOAD_CONFIG = "reload_config"
    
    # Risk management
    FREEZE = "freeze"
    UNFREEZE = "unfreeze"
    FORCECLOSE_POSITION = "forceclose_position"
    CANCEL_ORDER = "cancel_order"
    SET_RISK_LIMIT = "set_risk_limit"
    
    # Market control
    BLACKLIST_MARKET = "blacklist_market"
    WHITELIST_MARKET = "whitelist_market"
    
    # Confirmation
    CONFIRM_ACTION = "confirm_action"


@dataclass
class Action:
    """Base action class."""
    action_type: ActionType
    user_id: str
    timestamp: datetime
    metadata: Dict[str, Any]
    request_id: Optional[str] = None  # For tracking confirmations
    
    def __hash__(self):
        """Hash based on action_type, user_id, and timestamp."""
        return hash((self.action_type, self.user_id, self.timestamp))


@dataclass
class ControlAction(Action):
    """Control flow actions."""
    
    @staticmethod
    def start_bot(user_id: str) -> Action:
        return Action(
            action_type=ActionType.START_BOT,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={},
        )
    
    @staticmethod
    def pause_bot(user_id: str) -> Action:
        return Action(
            action_type=ActionType.PAUSE_BOT,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={},
        )
    
    @staticmethod
    def stop_bot(user_id: str) -> Action:
        return Action(
            action_type=ActionType.STOP_BOT,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={},
        )
    
    @staticmethod
    def change_mode(user_id: str, mode: str) -> Action:
        return Action(
            action_type=ActionType.CHANGE_MODE,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"mode": mode},
        )
    
    @staticmethod
    def reload_config(user_id: str) -> Action:
        return Action(
            action_type=ActionType.RELOAD_CONFIG,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={},
        )


@dataclass
class RiskAction(Action):
    """Risk management actions."""
    
    @staticmethod
    def freeze(user_id: str, scope: str, target: str) -> Action:
        """
        Freeze trading for a specific scope.
        
        Args:
            user_id: User performing the action
            scope: "event_id", "venue", or "all"
            target: The event_id, venue name, or empty string for "all"
        """
        return Action(
            action_type=ActionType.FREEZE,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"scope": scope, "target": target},
        )
    
    @staticmethod
    def unfreeze(user_id: str, scope: str, target: str) -> Action:
        """Remove freeze."""
        return Action(
            action_type=ActionType.UNFREEZE,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"scope": scope, "target": target},
        )
    
    @staticmethod
    def forceclose_position(user_id: str, position_id: str, request_id: str) -> Action:
        """Force close a position (requires 2-step confirmation)."""
        return Action(
            action_type=ActionType.FORCECLOSE_POSITION,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"position_id": position_id},
            request_id=request_id,
        )
    
    @staticmethod
    def cancel_order(user_id: str, order_id: str) -> Action:
        """Cancel an outstanding order."""
        return Action(
            action_type=ActionType.CANCEL_ORDER,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"order_id": order_id},
        )
    
    @staticmethod
    def set_risk_limit(user_id: str, limit_name: str, value: float) -> Action:
        """Update a risk limit."""
        return Action(
            action_type=ActionType.SET_RISK_LIMIT,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"limit_name": limit_name, "value": value},
        )


@dataclass
class ConfirmAction(Action):
    """Confirmation action for 2-step workflows."""
    
    @staticmethod
    def confirm(user_id: str, request_id: str, code: str) -> Action:
        return Action(
            action_type=ActionType.CONFIRM_ACTION,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            metadata={"request_id": request_id, "code": code},
            request_id=request_id,
        )


class ActionResult:
    """Result of executing an action."""
    
    def __init__(
        self,
        success: bool,
        message: str,
        action_id: Optional[str] = None,
        requires_confirmation: bool = False,
        confirmation_code: Optional[str] = None,
    ):
        self.success = success
        self.message = message
        self.action_id = action_id
        self.requires_confirmation = requires_confirmation
        self.confirmation_code = confirmation_code
        self.timestamp = datetime.utcnow()
