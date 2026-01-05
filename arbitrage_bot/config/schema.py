"""
Configuration schema and validation for Telegram interface.

Handles loading, validating, and persisting Telegram settings
with security considerations (never persisting tokens).
"""
import json
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationLevel(Enum):
    """Notification level."""
    ON = "on"
    SILENT = "silent"
    OFF = "off"


@dataclass
class NotificationSettings:
    """Granular notification control."""
    
    # Default level for all categories
    default_level: NotificationLevel = NotificationLevel.ON
    
    # Per-category overrides (None means use default_level)
    startup: Optional[NotificationLevel] = None
    warning: Optional[NotificationLevel] = None
    scan_opportunity: Optional[NotificationLevel] = None
    execution: Optional[NotificationLevel] = None
    fill: Optional[NotificationLevel] = None
    hedge: Optional[NotificationLevel] = None
    risk: Optional[NotificationLevel] = None
    pnl_update: Optional[NotificationLevel] = None
    strategy_msg: Optional[NotificationLevel] = None
    show_snapshot: Optional[NotificationLevel] = None
    
    def get_level(self, category: str) -> NotificationLevel:
        """Get notification level for a category."""
        level = getattr(self, category, None)
        if level is None:
            return self.default_level
        return level
    
    def is_enabled(self, category: str) -> bool:
        """Check if notifications for a category are enabled."""
        level = self.get_level(category)
        return level in (NotificationLevel.ON, NotificationLevel.SILENT)
    
    def should_notify(self, category: str) -> bool:
        """Check if we should send a notification (not silent)."""
        level = self.get_level(category)
        return level == NotificationLevel.ON
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "default_level": self.default_level.value,
            "startup": self.startup.value if self.startup else self.default_level.value,
            "warning": self.warning.value if self.warning else self.default_level.value,
            "scan_opportunity": self.scan_opportunity.value if self.scan_opportunity else self.default_level.value,
            "execution": self.execution.value if self.execution else self.default_level.value,
            "fill": self.fill.value if self.fill else self.default_level.value,
            "hedge": self.hedge.value if self.hedge else self.default_level.value,
            "risk": self.risk.value if self.risk else self.default_level.value,
            "pnl_update": self.pnl_update.value if self.pnl_update else self.default_level.value,
            "strategy_msg": self.strategy_msg.value if self.strategy_msg else self.default_level.value,
            "show_snapshot": self.show_snapshot.value if self.show_snapshot else self.default_level.value,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NotificationSettings":
        """Create from dictionary."""
        kwargs = {}
        for field_name in [
            "default_level", "startup", "warning", "scan_opportunity",
            "execution", "fill", "hedge", "risk", "pnl_update",
            "strategy_msg", "show_snapshot"
        ]:
            if field_name in data:
                value = data[field_name]
                if isinstance(value, str):
                    value = NotificationLevel(value)
                kwargs[field_name] = value
        
        return cls(**kwargs)


@dataclass
class TelegramConfig:
    """Telegram interface configuration."""
    
    enabled: bool = True
    token: str = ""  # Bot token (never persisted to file)
    chat_id: str = ""  # User or group chat ID
    topic_id: Optional[str] = None  # For group topics
    authorized_users: List[str] = field(default_factory=list)
    notification_settings: NotificationSettings = field(default_factory=NotificationSettings)
    
    def validate(self) -> tuple[bool, str]:
        """
        Validate configuration.
        
        Returns:
            (is_valid, error_message)
        """
        if self.enabled:
            if not self.token:
                return False, "Telegram token required when enabled"
            if not self.chat_id:
                return False, "Telegram chat_id required when enabled"
            if not isinstance(self.authorized_users, list):
                return False, "authorized_users must be a list"
        
        return True, ""
    
    def is_authorized(self, user_id: str) -> bool:
        """Check if user is authorized."""
        if not self.authorized_users:
            # Empty list means no one can control
            return False
        return str(user_id) in self.authorized_users
    
    def can_read_only(self) -> bool:
        """Check if read-only mode is allowed (always true for monitoring)."""
        return True
    
    def to_dict(self, include_token: bool = False) -> dict:
        """
        Convert to dictionary.
        
        Args:
            include_token: If False (default), token is omitted for safety
        """
        data = {
            "enabled": self.enabled,
            "chat_id": self.chat_id,
            "topic_id": self.topic_id,
            "authorized_users": self.authorized_users,
            "notification_settings": self.notification_settings.to_dict(),
        }
        
        if include_token:
            data["token"] = self.token
        
        return data
    
    @classmethod
    def from_dict(cls, data: dict, token: Optional[str] = None) -> "TelegramConfig":
        """
        Create from dictionary.
        
        Args:
            data: Configuration dictionary (from JSON)
            token: Token (passed separately, not in JSON)
        """
        token = token or data.get("token", "")
        
        notification_settings = NotificationSettings.from_dict(
            data.get("notification_settings", {})
        )
        
        return cls(
            enabled=data.get("enabled", True),
            token=token,
            chat_id=data.get("chat_id", ""),
            topic_id=data.get("topic_id"),
            authorized_users=data.get("authorized_users", []),
            notification_settings=notification_settings,
        )


class TelegramConfigLoader:
    """Load and persist Telegram configuration."""
    
    @staticmethod
    def load_from_file(config_path: str, token: Optional[str] = None) -> Optional[TelegramConfig]:
        """
        Load configuration from JSON file.
        
        Args:
            config_path: Path to telegram_config.json
            token: Token (from environment or other source)
            
        Returns:
            TelegramConfig or None if file not found/invalid
        """
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            
            config = TelegramConfig.from_dict(data, token=token)
            is_valid, error_msg = config.validate()
            
            if not is_valid:
                logger.error(f"Invalid Telegram config: {error_msg}")
                return None
            
            logger.info("Telegram config loaded successfully")
            return config
            
        except FileNotFoundError:
            logger.warning(f"Telegram config file not found: {config_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in Telegram config: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading Telegram config: {e}")
            return None
    
    @staticmethod
    def save_to_file(config: TelegramConfig, config_path: str, include_token: bool = False):
        """
        Save configuration to JSON file.
        
        IMPORTANT: Never include token in persisted file.
        
        Args:
            config: Configuration to save
            config_path: Path to save to
            include_token: If False (default), token is omitted
        """
        try:
            data = config.to_dict(include_token=include_token)
            
            with open(config_path, "w") as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Telegram config saved to {config_path}")
            
        except Exception as e:
            logger.error(f"Error saving Telegram config: {e}")
