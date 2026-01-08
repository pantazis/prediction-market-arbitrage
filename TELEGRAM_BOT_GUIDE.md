# Telegram Bot Guide

## Two Bot Modes

This codebase has **two different ways** to run the arbitrage bot:

### 1. Standard CLI Bot (`python -m predarb run`)
- **Location**: `src/predarb/`
- **Features**: Detects arbitrage, executes trades, sends notifications
- **Telegram**: One-way notifications only (opportunities, trades, errors)
- **Commands**: NOT supported (no `/status`, `/start`, `/stop` etc.)
- **Use case**: Simple automated trading bot

### 2. Telegram-Controlled Bot (`arbitrage_bot/main.py`)
- **Location**: `arbitrage_bot/`  
- **Features**: Full interactive Telegram interface with 40+ commands
- **Telegram**: Two-way communication (send commands, get responses)
- **Commands**: ✅ Full support (`/status`, `/start`, `/pause`, `/balance`, etc.)
- **Use case**: Interactive bot control and monitoring via Telegram

## Why /status Doesn't Work

If you're running `python -m predarb run`, the `/status` command **won't work** because:
- This mode only sends notifications (one-way)
- It doesn't listen for incoming Telegram messages
- Commands like `/status`, `/balance`, `/positions` are not supported

## How to Use Telegram Commands

To use commands like `/status`, you need to run the **Telegram-Controlled Bot**:

### Setup

1. **Set environment variables:**
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   export TELEGRAM_CHAT_ID="your_chat_id_here"
   ```

2. **Create telegram_config.json** in the project root:
   ```json
   {
     "bot_token": "${TELEGRAM_BOT_TOKEN}",
     "authorized_users": ["your_telegram_user_id"],
     "notification_settings": {
       "startup": "on",
       "shutdown": "on",
       "warning": "on",
       "scan_opportunity": "on",
       "risk_rejection": "off",
       "default": "on"
     },
     "rate_limits": {
       "status": {"max_per_minute": 10},
       "balance": {"max_per_minute": 5},
       "default": {"max_per_minute": 20}
     }
   }
   ```

3. **Run the Telegram-controlled bot:**
   ```python
   # Create a script: run_telegram_bot.py
   import asyncio
   from arbitrage_bot.main import TelegramControlledArbitrageBot
   
   async def main():
       # Your state_getter function here (returns BotSnapshot)
       bot = TelegramControlledArbitrageBot(
           telegram_config_path="telegram_config.json",
           state_getter=your_state_getter_function
       )
       await bot.start()
   
   if __name__ == "__main__":
       asyncio.run(main())
   ```

### Available Commands

Once running, you can use these Telegram commands:

**SYSTEM & CONTROL:**
- `/start` - Start bot loop
- `/pause` - Pause new trades (risk mgmt active)
- `/stop` - Stop bot loop
- `/mode <scan-only|paper|live>` - Change operating mode
- `/reload_config` - Reload config from disk
- `/help` - Show all commands

**MONITORING:**
- `/status [table]` - Show bot status or table view
- `/balance` - Show USDC balance
- `/positions [n]` - Show last n open positions
- `/orders [n]` - Show outstanding orders
- `/profit [n]` - Show PnL summary
- `/daily [n]` `/weekly [n]` `/monthly [n]` - PnL by period
- `/performance` - Per-market statistics
- `/risk` - Risk limits and utilization
- `/show_config` - Show configuration

**ACTIONS:**
- `/freeze <event|venue|all> [target]` - Freeze trading
- `/unfreeze <event|venue|all> [target]` - Unfreeze trading
- `/forceclose [position|all]` - Force close positions
- `/cancel [order|all]` - Cancel orders
- `/set_limit <name> <value>` - Update risk limits
- `/simulate <on|off>` - Toggle paper mode

**DEBUG:**
- `/opps [n]` - Last n opportunities
- `/why <opp_id>` - Decision trace
- `/markets [filter]` - List monitored markets
- `/health` - System health check
- `/tg_info` - Show chat_id and topic_id

## Quick Migration

If you want to keep using `python -m predarb run` but add command support:

**Option A: Run both bots**
- Keep running `python -m predarb run` for trading
- Run a separate Telegram listener bot for commands
- Commands would query state from the main bot

**Option B: Switch to Telegram-Controlled Bot**
- Integrate your trading logic into `TelegramControlledArbitrageBot`
- Benefit from full command interface
- More complex setup but better control

## Current Bot Behavior

Since you're likely running `python -m predarb run`:
- ✅ Opportunity notifications work (with new status labels!)
- ✅ Trade notifications work
- ✅ Error notifications work
- ❌ Commands like `/status` don't work
- ❌ Two-way communication not supported

## Recent Improvements (Just Added!)

Even without `/status` support, your notifications are now **better**:

### Old Format:
```
🔎 Opportunity DUPLICATE
Markets: 0x7130b8d9bb59393ede189911ba57783debc1900dffb8143c3cb0027952e2f7df, 0xdc0a4c64465923ef51a0609b706ac5f23a56b590b7e660ba5303bded0d7a90b7
Edge: 0.3825
Details: Duplicate price gap 0.385 vs 0.003
```

### New Format:
```
🔎 Opportunity DUPLICATE 🟢 GREAT
Markets: 0x7130b8...e2f7df, 0xdc0a4c6...a90b7
Edge: 38.25% (Est. gain: $38.25 per $100)
Details: Duplicate: 38.5% vs 0.3% (gap: 38.2%, $38.20/$100)
```

**Status Labels:**
- 🟢 GREAT: Edge >= 5%
- 🟡 MEDIUM: Edge >= 2%
- 🔴 BAD: Edge < 2%

## Next Steps

1. **To get `/status` working**: Follow the "Telegram-Controlled Bot" setup above
2. **To stick with current setup**: Notifications now show better info (status, %, $)
3. **Questions?**: Check `arbitrage_bot/README.md` or `CODEBASE_OPERATIONS.json`

---

**TL;DR**: `/status` only works with `arbitrage_bot/main.py`, not `python -m predarb run`. But notifications are now way more readable!
