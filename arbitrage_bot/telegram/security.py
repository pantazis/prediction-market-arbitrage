"""
Security utilities for Telegram interface.

Handles user authorization, confirmation codes, and safe error responses.
"""
import logging
import secrets
import string
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)


class AuthorizationGate:
    """Manages authorization checks and read-only mode."""
    
    def __init__(self, authorized_users: list):
        """
        Initialize authorization gate.
        
        Args:
            authorized_users: List of authorized user IDs
        """
        self.authorized_users = set(str(uid) for uid in authorized_users)
    
    def is_authorized(self, user_id: str) -> bool:
        """Check if user is authorized for control commands."""
        return str(user_id) in self.authorized_users
    
    def can_read_status(self, user_id: str) -> bool:
        """Anyone can read status (read-only mode)."""
        return True
    
    def can_execute_action(self, user_id: str) -> bool:
        """Only authorized users can execute actions."""
        return self.is_authorized(user_id)
    
    def deny_message(self) -> str:
        """Get a denial message for unauthorized access."""
        return "❌ Unauthorized."


class ConfirmationManager:
    """Manages 2-step confirmation for risky actions."""
    
    def __init__(self, code_length: int = 6, expiry_seconds: int = 300):
        """
        Initialize confirmation manager.
        
        Args:
            code_length: Length of confirmation code
            expiry_seconds: Time before confirmation expires
        """
        self.code_length = code_length
        self.expiry_seconds = expiry_seconds
        self.pending: Dict[str, Dict] = {}  # request_id -> {code, user_id, action, expiry}
    
    def create_confirmation(self, user_id: str, action: str) -> Tuple[str, str]:
        """
        Create a confirmation code for an action.
        
        Args:
            user_id: User requesting confirmation
            action: Action description (e.g., "forceclose_all")
            
        Returns:
            (request_id, code)
        """
        request_id = secrets.token_hex(8)
        code = "".join(
            secrets.choice(string.digits) 
            for _ in range(self.code_length)
        )
        
        self.pending[request_id] = {
            "code": code,
            "user_id": user_id,
            "action": action,
            "expiry": datetime.utcnow() + timedelta(seconds=self.expiry_seconds),
        }
        
        logger.debug(
            f"Confirmation created",
            extra={"request_id": request_id, "user_id": user_id}
        )
        
        return request_id, code
    
    def verify_confirmation(self, request_id: str, user_id: str, code: str) -> Tuple[bool, str]:
        """
        Verify a confirmation code.
        
        Args:
            request_id: Request ID from confirmation
            user_id: User submitting confirmation
            code: Code provided by user
            
        Returns:
            (is_valid, message)
        """
        if request_id not in self.pending:
            return False, "❌ Invalid confirmation request."
        
        pending = self.pending[request_id]
        
        # Check expiry
        if datetime.utcnow() >= pending["expiry"]:
            del self.pending[request_id]
            return False, "❌ Confirmation expired."
        
        # Check user matches
        if str(pending["user_id"]) != str(user_id):
            return False, "❌ User mismatch."
        
        # Check code
        if pending["code"] != code:
            return False, "❌ Invalid code."
        
        # Valid!
        action = pending["action"]
        del self.pending[request_id]
        
        logger.info(
            f"Confirmation verified",
            extra={"request_id": request_id, "user_id": user_id, "action": action}
        )
        
        return True, f"✅ Confirmed: {action}"
    
    def cancel_confirmation(self, request_id: str):
        """Cancel a pending confirmation."""
        if request_id in self.pending:
            del self.pending[request_id]
    
    def cleanup_expired(self):
        """Remove expired confirmations."""
        now = datetime.utcnow()
        expired = [
            rid for rid, data in self.pending.items()
            if now > data["expiry"]
        ]
        for rid in expired:
            del self.pending[rid]


class SafeMessageFormatter:
    """Format error and status messages safely (no secrets, structured)."""
    
    @staticmethod
    def error_message(error: Exception, safe_only: bool = True) -> str:
        """
        Format an error message safely.
        
        Args:
            error: The exception
            safe_only: If True, return generic message; if False, include error type
            
        Returns:
            Safe error message
        """
        if safe_only:
            return "❌ An error occurred. Check logs for details."
        else:
            return f"❌ {type(error).__name__}: {str(error)[:100]}"
    
    @staticmethod
    def sanitize_config_for_display(config_dict: dict) -> dict:
        """
        Remove sensitive information from config before displaying.
        
        Args:
            config_dict: Configuration dictionary
            
        Returns:
            Sanitized dictionary with secrets removed
        """
        sensitive_keys = {
            "token", "secret", "api_key", "api_secret",
            "password", "private_key", "seed_phrase"
        }
        
        sanitized = {}
        for key, value in config_dict.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = SafeMessageFormatter.sanitize_config_for_display(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    @staticmethod
    def format_quantity(value: float, decimals: int = 2) -> str:
        """Format a quantity nicely."""
        return f"{value:,.{decimals}f}"
    
    @staticmethod
    def format_percentage(value: float, decimals: int = 2) -> str:
        """Format a percentage nicely."""
        return f"{value:.{decimals}f}%"
    
    @staticmethod
    def format_time_delta(seconds: float) -> str:
        """Format a time delta nicely."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
