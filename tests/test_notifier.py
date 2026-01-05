import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from predarb.notifier import TelegramNotifier
from predarb.models import Opportunity, TradeAction


def test_telegram_notifier_sends_request():
    notifier = TelegramNotifier(bot_token="token", chat_id="chat")
    opp = Opportunity(
        type="PARITY",
        market_ids=["m1"],
        description="desc",
        net_edge=0.1,
        actions=[TradeAction(market_id="m1", outcome_id="o1", side="BUY", amount=1.0, limit_price=0.5)],
    )
    with mock.patch("predarb.notifier.requests.post") as post:
        post.return_value.raise_for_status = lambda: None
        notifier.notify_opportunity(opp)
        post.assert_called_once()
        args, kwargs = post.call_args
        assert "sendMessage" in args[0]
        assert kwargs["json"]["chat_id"] == "chat"


def test_telegram_notifier_handles_errors():
    notifier = TelegramNotifier(bot_token="token", chat_id="chat")
    with mock.patch("predarb.notifier.requests.post", side_effect=Exception("fail")):
        # Should not raise
        notifier.notify_error("boom", "ctx")
