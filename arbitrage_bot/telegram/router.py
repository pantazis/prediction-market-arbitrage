"""
Command router and parser for Telegram interface.

Maps user input to handler functions and validates arguments.
"""
import logging
import re
from typing import Dict, Callable, Optional, Tuple, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedCommand:
    """Result of parsing a command."""
    command: str
    args: List[str]
    raw_text: str
    
    def get_arg(self, index: int, default: Optional[str] = None) -> Optional[str]:
        """Get argument by index."""
        if index < len(self.args):
            return self.args[index]
        return default
    
    def get_arg_int(self, index: int, default: int = 0) -> int:
        """Get argument as integer."""
        arg = self.get_arg(index)
        if arg is None:
            return default
        try:
            return int(arg)
        except ValueError:
            return default
    
    def get_arg_float(self, index: int, default: float = 0.0) -> float:
        """Get argument as float."""
        arg = self.get_arg(index)
        if arg is None:
            return default
        try:
            return float(arg)
        except ValueError:
            return default
    
    def join_args(self, start_index: int = 0) -> str:
        """Join remaining arguments."""
        return " ".join(self.args[start_index:])


class CommandParser:
    """Parse Telegram messages into commands."""
    
    # Command pattern: /command or /command@botname
    COMMAND_PATTERN = re.compile(r"^/([a-z_]+)(?:@\w+)?\s*(.*?)$", re.IGNORECASE)
    
    @staticmethod
    def parse(text: str) -> Optional[ParsedCommand]:
        """
        Parse a message into a command.
        
        Args:
            text: User message text
            
        Returns:
            ParsedCommand if valid command, None otherwise
        """
        text = text.strip()
        match = CommandParser.COMMAND_PATTERN.match(text)
        
        if not match:
            return None
        
        command = match.group(1).lower()
        args_text = match.group(2).strip()
        
        # Parse arguments (space-separated, quoted strings allowed)
        args = CommandParser._parse_args(args_text)
        
        return ParsedCommand(
            command=command,
            args=args,
            raw_text=text,
        )
    
    @staticmethod
    def _parse_args(args_text: str) -> List[str]:
        """Parse arguments, respecting quoted strings."""
        if not args_text:
            return []
        
        args = []
        current = ""
        in_quotes = False
        
        for char in args_text:
            if char == '"' and (not current or current[-1] != "\\"):
                in_quotes = not in_quotes
            elif char == " " and not in_quotes:
                if current:
                    args.append(current)
                    current = ""
            else:
                current += char
        
        if current:
            args.append(current)
        
        return args


class CommandRouter:
    """Route parsed commands to handler functions."""
    
    def __init__(self):
        """Initialize router."""
        self.handlers: Dict[str, Callable] = {}
        self.help_texts: Dict[str, str] = {}
    
    def register(
        self,
        command: str,
        handler: Callable,
        help_text: str = "",
    ) -> "CommandRouter":
        """
        Register a command handler.
        
        Args:
            command: Command name (without /)
            handler: Async function(parsed_cmd: ParsedCommand) -> str
            help_text: Help text for /help command
            
        Returns:
            Self for chaining
        """
        self.handlers[command.lower()] = handler
        if help_text:
            self.help_texts[command.lower()] = help_text
        
        logger.debug(f"Registered command: {command}")
        return self
    
    async def route(self, parsed_cmd: ParsedCommand) -> str:
        """
        Route a parsed command to its handler.
        
        Args:
            parsed_cmd: Parsed command
            
        Returns:
            Response text from handler, or error message
        """
        command = parsed_cmd.command.lower()
        
        if command not in self.handlers:
            # Try fuzzy matching for common aliases
            fuzzy = self._fuzzy_match(command)
            if fuzzy:
                command = fuzzy
            else:
                return f"❌ Unknown command: /{command}\nUse /help for available commands."
        
        try:
            handler = self.handlers[command]
            response = await handler(parsed_cmd)
            return response or "✅"
        except Exception as e:
            logger.error(f"Error in command handler for {command}: {e}", exc_info=True)
            return f"❌ Error executing command. Check logs."
    
    def _fuzzy_match(self, command: str) -> Optional[str]:
        """Try to fuzzy match a command."""
        # Common aliases
        aliases = {
            "status_table": "status",
            "stat": "status",
            "pos": "positions",
            "ord": "orders",
            "opp": "opps",
            "conf": "confirm",
            "conf_action": "confirm",
        }
        
        if command in aliases:
            return aliases[command]
        
        # Try prefix matching
        for registered in self.handlers:
            if registered.startswith(command):
                return registered
        
        return None
    
    def get_help(self) -> str:
        """Get help text for all commands."""
        lines = ["📖 Available Commands:\n"]
        
        # Organize by category
        categories = {
            "SYSTEM": [
                "start", "pause", "stop", "mode", "reload_config", "help"
            ],
            "STATUS": [
                "status", "balance", "positions", "orders", "profit",
                "daily", "weekly", "monthly", "performance", "risk", "show_config"
            ],
            "ACTION": [
                "freeze", "unfreeze", "forceclose", "cancel", "set_limit", "simulate"
            ],
            "DEBUG": [
                "opps", "why", "markets", "health", "tg_info"
            ],
            "CONFIRMATION": [
                "confirm"
            ],
        }
        
        for category, commands in categories.items():
            lines.append(f"\n**{category}:**")
            for cmd in commands:
                if cmd in self.help_texts:
                    lines.append(f"  /{cmd} - {self.help_texts[cmd]}")
                else:
                    lines.append(f"  /{cmd}")
        
        return "\n".join(lines)
    
    def list_commands(self) -> List[str]:
        """List all registered commands."""
        return sorted(self.handlers.keys())
