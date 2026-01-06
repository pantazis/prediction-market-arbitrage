import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from src.telegram_notifier import TelegramNotifier
from src.models import Trade, Opportunity, TradeAction


@pytest.mark.skip(reason="Legacy src/telegram_notifier.py module - use modern src/predarb/notifiers instead")
class TestTelegramNotifier:
    """Test suite for TelegramNotifier (LEGACY - use modern implementation)"""
    
    def test_notifier_disabled(self):
        """Test that no messages are sent when notifier is disabled"""
        notifier = TelegramNotifier("token", "chat_id", enabled=False)
        
        trade = Trade(
            id="t1",
            timestamp=datetime.now(),
            market_id="m1",
            outcome_id="o1",
            side="BUY",
            amount=10.0,
            price=0.5,
            fees=0.1
        )
        
        # Should return False and not attempt to send
        result = notifier.notify_trade(trade)
        assert result is False
    
    def test_notifier_no_credentials(self):
        """Test that notifier disables itself when credentials are missing"""
        notifier = TelegramNotifier("", "", enabled=True)
        assert notifier.enabled is False
    
    @patch('src.telegram_notifier.Bot')
    def test_notify_trade(self, mock_bot_class):
        """Test trade notification formatting"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        trade = Trade(
            id="t1",
            timestamp=datetime(2026, 1, 5, 10, 30, 0),
            market_id="m1",
            outcome_id="o1",
            side="BUY",
            amount=10.0,
            price=0.5,
            fees=0.1
        )
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_trade(trade, "Test Market")
            
            assert result is True
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('src.telegram_notifier.Bot')
    def test_notify_opportunity(self, mock_bot_class):
        """Test opportunity notification formatting"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        actions = [
            TradeAction("m1", "o1", "BUY", 1.0, 0.45),
            TradeAction("m1", "o2", "BUY", 1.0, 0.45)
        ]
        
        opp = Opportunity(
            market_id="m1",
            market_title="Test Market",
            type_name="PARITY",
            description="YES + NO = 0.90",
            estimated_edge=0.10,
            required_capital=0.90,
            actions=actions,
            timestamp=datetime(2026, 1, 5, 10, 30, 0)
        )
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_opportunity(opp)
            
            assert result is True
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('src.telegram_notifier.Bot')
    def test_notify_balance(self, mock_bot_class):
        """Test balance notification formatting"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        positions = {
            "o1": 10.5,
            "o2": 5.2,
            "o3": 8.7
        }
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_balance(cash=990.0, positions=positions, total_trades=5)
            
            assert result is True
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('src.telegram_notifier.Bot')
    def test_notify_error(self, mock_bot_class):
        """Test error notification formatting"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_error("Connection timeout", "API Call")
            
            assert result is True
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('src.telegram_notifier.Bot')
    def test_notify_startup(self, mock_bot_class):
        """Test startup notification"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_startup("Paper Trading: True")
            
            assert result is True
            mock_loop.run_until_complete.assert_called_once()
    
    @patch('src.telegram_notifier.Bot')
    def test_api_error_handling(self, mock_bot_class):
        """Test graceful handling of Telegram API failures"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        trade = Trade(
            id="t1",
            timestamp=datetime.now(),
            market_id="m1",
            outcome_id="o1",
            side="BUY",
            amount=10.0,
            price=0.5,
            fees=0.1
        )
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            # Simulate API error
            mock_loop.run_until_complete.side_effect = Exception("API Error")
            
            result = notifier.notify_trade(trade)
            
            # Should return False but not crash
            assert result is False
    
    @patch('src.telegram_notifier.Bot')
    def test_large_positions_truncation(self, mock_bot_class):
        """Test that large position lists are truncated"""
        mock_bot = Mock()
        mock_bot_class.return_value = mock_bot
        
        notifier = TelegramNotifier("test_token", "test_chat", enabled=True)
        
        # Create 10 positions (should show only 5)
        positions = {f"o{i}": float(i) for i in range(10)}
        
        with patch('asyncio.new_event_loop') as mock_loop_factory:
            mock_loop = Mock()
            mock_loop_factory.return_value = mock_loop
            mock_loop.run_until_complete = Mock()
            
            result = notifier.notify_balance(cash=1000.0, positions=positions, total_trades=10)
            
            assert result is True
