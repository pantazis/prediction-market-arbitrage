"""
Rate limiting for command execution.

Prevents abuse and ensures safe operation by limiting:
- Overall command rate
- Per-command rate
- Per-user rate
- Dangerous command frequency
"""
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CommandRisk(Enum):
    """Risk level of a command."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Command risk classification
COMMAND_RISK = {
    # Low risk - read-only
    "help": CommandRisk.LOW,
    "status": CommandRisk.LOW,
    "status_table": CommandRisk.LOW,
    "balance": CommandRisk.LOW,
    "positions": CommandRisk.LOW,
    "orders": CommandRisk.LOW,
    "profit": CommandRisk.LOW,
    "daily": CommandRisk.LOW,
    "weekly": CommandRisk.LOW,
    "monthly": CommandRisk.LOW,
    "performance": CommandRisk.LOW,
    "risk": CommandRisk.LOW,
    "show_config": CommandRisk.LOW,
    "opps": CommandRisk.LOW,
    "why": CommandRisk.LOW,
    "markets": CommandRisk.LOW,
    "health": CommandRisk.LOW,
    "tg_info": CommandRisk.LOW,
    
    # Medium risk - state change
    "start": CommandRisk.MEDIUM,
    "pause": CommandRisk.MEDIUM,
    "stop": CommandRisk.MEDIUM,
    "mode": CommandRisk.MEDIUM,
    "reload_config": CommandRisk.MEDIUM,
    "simulate": CommandRisk.MEDIUM,
    
    # High risk - irreversible or dangerous
    "freeze": CommandRisk.HIGH,
    "unfreeze": CommandRisk.MEDIUM,
    "forceclose": CommandRisk.HIGH,
    "cancel": CommandRisk.MEDIUM,
    "set_limit": CommandRisk.MEDIUM,
    "blacklist": CommandRisk.HIGH,
    "whitelist": CommandRisk.MEDIUM,
    "confirm": CommandRisk.HIGH,
}


class RateLimiter:
    """Rate limit command execution."""
    
    def __init__(
        self,
        global_rate: int = 100,  # commands per minute
        per_user_rate: int = 20,  # commands per minute
        high_risk_rate: int = 2,  # high risk commands per minute
        medium_risk_rate: int = 5,  # medium risk commands per minute
    ):
        """
        Initialize rate limiter.
        
        Args:
            global_rate: Max commands per minute (all users)
            per_user_rate: Max commands per minute (per user)
            high_risk_rate: Max high-risk commands per minute (per user)
            medium_risk_rate: Max medium-risk commands per minute (per user)
        """
        self.global_rate = global_rate
        self.per_user_rate = per_user_rate
        self.high_risk_rate = high_risk_rate
        self.medium_risk_rate = medium_risk_rate
        
        # Track: command_name -> [(timestamp, user_id)]
        self.global_history: Dict[str, list] = {}
        
        # Track: user_id -> [(timestamp, command_name)]
        self.user_history: Dict[str, list] = {}
    
    def is_allowed(self, command: str, user_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a command is allowed.
        
        Args:
            command: Command name
            user_id: User executing command
            
        Returns:
            (is_allowed, reason_if_denied)
        """
        now = datetime.utcnow()
        risk = COMMAND_RISK.get(command, CommandRisk.MEDIUM)
        
        # Clean old history
        self._cleanup_old_history(now)
        
        # Check global rate
        if not self._check_global_rate(command, now):
            msg = f"Global rate limit exceeded for {command}"
            logger.warning(msg)
            return False, "⏱️ Rate limit exceeded. Try again later."
        
        # Check per-user rate
        if not self._check_per_user_rate(user_id, now):
            msg = f"Per-user rate limit exceeded for {user_id}"
            logger.warning(msg)
            return False, "⏱️ You're sending commands too fast. Try again later."
        
        # Check risk-specific rate
        if risk == CommandRisk.HIGH:
            if not self._check_high_risk_rate(user_id, now):
                msg = f"High-risk rate limit exceeded for {user_id}"
                logger.warning(msg)
                return False, "⏱️ This action is rate-limited. Try again later."
        elif risk == CommandRisk.MEDIUM:
            if not self._check_medium_risk_rate(user_id, now):
                msg = f"Medium-risk rate limit exceeded for {user_id}"
                logger.warning(msg)
                return False, "⏱️ This action is rate-limited. Try again later."
        
        # Record this command
        self._record_command(command, user_id, now)
        
        return True, None
    
    def _check_global_rate(self, command: str, now: datetime) -> bool:
        """Check global rate limit."""
        if command not in self.global_history:
            return True
        
        recent = [
            ts for ts in self.global_history[command]
            if now - ts < timedelta(minutes=1)
        ]
        
        return len(recent) < self.global_rate
    
    def _check_per_user_rate(self, user_id: str, now: datetime) -> bool:
        """Check per-user rate limit."""
        if user_id not in self.user_history:
            return True
        
        recent = [
            ts for cmd, ts in self.user_history[user_id]
            if now - ts < timedelta(minutes=1)
        ]
        
        return len(recent) < self.per_user_rate
    
    def _check_high_risk_rate(self, user_id: str, now: datetime) -> bool:
        """Check high-risk command rate."""
        if user_id not in self.user_history:
            return True
        
        recent_high_risk = [
            ts for cmd, ts in self.user_history[user_id]
            if now - ts < timedelta(minutes=1)
            and COMMAND_RISK.get(cmd, CommandRisk.MEDIUM) == CommandRisk.HIGH
        ]
        
        return len(recent_high_risk) < self.high_risk_rate
    
    def _check_medium_risk_rate(self, user_id: str, now: datetime) -> bool:
        """Check medium-risk command rate."""
        if user_id not in self.user_history:
            return True
        
        recent_medium_risk = [
            cmd for cmd, ts in self.user_history[user_id]
            if now - ts < timedelta(minutes=1)
            and COMMAND_RISK.get(cmd, CommandRisk.MEDIUM) == CommandRisk.MEDIUM
        ]
        
        return len(recent_medium_risk) < self.medium_risk_rate
    
    def _record_command(self, command: str, user_id: str, now: datetime):
        """Record a command execution."""
        # Global history
        if command not in self.global_history:
            self.global_history[command] = []
        self.global_history[command].append(now)
        
        # User history (track as tuple: command, timestamp)
        if user_id not in self.user_history:
            self.user_history[user_id] = []
        self.user_history[user_id].append((command, now))
    
    def _cleanup_old_history(self, now: datetime):
        """Remove entries older than 2 minutes (with some buffer)."""
        cutoff = now - timedelta(minutes=2)
        
        # Clean global history
        for command in list(self.global_history.keys()):
            self.global_history[command] = [
                ts for ts in self.global_history[command]
                if ts > cutoff
            ]
            if not self.global_history[command]:
                del self.global_history[command]
        
        # Clean user history
        for user_id in list(self.user_history.keys()):
            self.user_history[user_id] = [
                (cmd, ts) for cmd, ts in self.user_history[user_id]
                if ts > cutoff
            ]
            if not self.user_history[user_id]:
                del self.user_history[user_id]
    
    def stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "global_history_entries": sum(len(v) for v in self.global_history.values()),
            "user_history_entries": sum(len(v) for v in self.user_history.values()),
            "tracked_users": len(self.user_history),
        }
