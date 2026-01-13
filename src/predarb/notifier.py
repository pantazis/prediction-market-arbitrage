from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from predarb.models import Opportunity

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def _post(self, text: str):
        try:
            resp = requests.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=5,
            )
            resp.raise_for_status()
        except Exception as e:
            logger.warning("Telegram send failed: %s", e)

    def notify_startup(self, message: str):
        self._post(f"📈 Predarb started\n{message}")

    def notify_error(self, message: str, context: Optional[str] = None):
        prefix = f"❗ Error in {context}: " if context else "❗ Error: "
        self._post(prefix + message)

    def notify_opportunity(self, opp: Opportunity):
        # Classify opportunity quality based on edge
        edge_pct = opp.net_edge * 100
        if edge_pct >= 5.0:
            status = "🟢 GREAT"
        elif edge_pct >= 2.0:
            status = "🟡 MEDIUM"
        else:
            status = "🔴 BAD"
        
        # Format edge as percentage with gains estimate
        edge_str = f"{edge_pct:.2f}%"
        
        # Estimate profit in dollars (assuming $100 trade size for reference)
        estimated_gain = opp.net_edge * 100
        gain_str = f"${estimated_gain:.2f} per $100"
        
        # Get market titles from metadata if available
        market_titles = opp.metadata.get("market_titles", [])
        if market_titles:
            # Show first title, or indicate multiple
            if len(market_titles) == 1:
                title_str = market_titles[0][:80] + "..." if len(market_titles[0]) > 80 else market_titles[0]
            else:
                title_str = f"{market_titles[0][:60]}... (+{len(market_titles)-1} more)"
        else:
            title_str = None
        
        # Format market IDs (shorten if they're hashes)
        market_ids = opp.market_ids
        if len(market_ids) > 0 and len(market_ids[0]) > 20:
            # Likely hashes, show shortened version
            markets_str = ", ".join([m[:8] + "..." + m[-6:] for m in market_ids])
        else:
            markets_str = ", ".join(market_ids)
        
        # Format trade actions (BUY/SELL sides)
        actions_str = []
        for i, action in enumerate(opp.actions, 1):
            side_emoji = "📗" if action.side.upper() == "BUY" else "📕"
            # Try to show outcome ID in a readable way
            outcome = action.outcome_id if len(action.outcome_id) <= 8 else action.outcome_id[:6] + "..."
            actions_str.append(f"{side_emoji} {action.side} {outcome} @ {action.limit_price:.3f}")
        trades_str = " vs ".join(actions_str) if len(actions_str) <= 3 else f"{len(actions_str)} trades"
        
        execution = opp.metadata.get("execution", {})
        trades = opp.metadata.get("trades", [])
        risk = opp.metadata.get("risk_approval", {})
        risk_note = "yes" if risk.get("approved") else "no"
        exec_status = execution.get("status", "unknown")
        filled = execution.get("total_filled")
        intended = execution.get("total_intended")
        pnl = execution.get("realized_pnl")

        lines = [
            f"🔎 Opportunity {opp.type} {status}",
            f"✅ 5. Risk approval | {risk_note}",
        ]
        if title_str:
            lines.append(f"Market: {title_str}")
        lines.extend([
            f"Trades: {trades_str}",
            f"IDs: {markets_str}",
            f"Edge: {edge_str} (Est. gain: {gain_str})",
            f"Details: {opp.description}",
        ])
        if intended is not None and filled is not None:
            lines.append(f"🧾 6. Paper trade | {exec_status} | filled {filled:.4f}/{intended:.4f}")
        if pnl is not None:
            lines.append(f"🧾 6. PnL | {pnl:.4f}")
        if trades:
            trade_lines = []
            for t in trades[:3]:
                trade_lines.append(
                    f"{t.get('side','')} {t.get('outcome_id','')} @ {t.get('price',0):.4f} x {t.get('amount',0):.4f}"
                )
            if len(trades) > 3:
                trade_lines.append(f"... +{len(trades)-3} more")
            lines.append("🧾 6. Trade details | " + "; ".join(trade_lines))
        self._post("\n".join(lines))

    def notify_trade_summary(self, count: int):
        self._post(f"✅ Executed {count} opportunities this iteration.")

    def notify_filtering(self, total: int, eligible: int, ranked: int, high_quality: int):
        lines = [
            "🔍 Market Filtering Results",
            f"Total markets: {total}",
            f"Eligible markets: {eligible}",
            f"Ranked markets: {ranked}",
            f"High-quality markets: {high_quality}",
        ]
        self._post("\n".join(lines))

    def notify_cross_venue_matches(self, pairs):
        def _shorten(text: object, limit: int = 80) -> str:
            raw = str(text) if text is not None else ""
            return raw if len(raw) <= limit else raw[: max(0, limit - 3)] + "..."

        lines = [f"🔗 1. Cross-venue matcher ({len(pairs)})"]
        for idx, (k_market, p_market, score) in enumerate(pairs, 1):
            k_title = _shorten(getattr(k_market, "question", None) or getattr(k_market, "id", ""))
            p_title = _shorten(getattr(p_market, "question", None) or getattr(p_market, "id", ""))
            time_note = ""
            try:
                k_end = getattr(k_market, "end_date", None)
                p_end = getattr(p_market, "end_date", None)
                if k_end and p_end:
                    hours = abs((k_end - p_end).total_seconds()) / 3600.0
                    time_note = f" | Δt={hours:.1f}h"
            except Exception:
                time_note = ""
            lines.append(f"{idx}. {score:.2f} | K: {k_title} | P: {p_title}{time_note}")

        max_len = 3500
        chunk: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk and chunk_len + len(line) + 1 > max_len:
                self._post("\n".join(chunk))
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            self._post("\n".join(chunk))

    def notify_cross_venue_verification(self, results):
        def _shorten(text: object, limit: int = 80) -> str:
            raw = str(text) if text is not None else ""
            return raw if len(raw) <= limit else raw[: max(0, limit - 3)] + "..."

        lines = [f"✅ 2. LLM verification ({len(results)})"]
        for idx, (k_market, p_market, score, verdict) in enumerate(results, 1):
            status = "PASS" if verdict.same_event else "FAIL"
            k_title = _shorten(getattr(k_market, "question", None) or getattr(k_market, "id", ""))
            p_title = _shorten(getattr(p_market, "question", None) or getattr(p_market, "id", ""))
            reason = _shorten(getattr(verdict, "reason", "") or "n/a")
            lines.append(
                f"{idx}. {status} | sim={score:.2f} conf={verdict.confidence:.2f} | "
                f"K: {k_title} | P: {p_title} | Reason: {reason}"
            )

        max_len = 3500
        chunk: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk and chunk_len + len(line) + 1 > max_len:
                self._post("\n".join(chunk))
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            self._post("\n".join(chunk))

    def notify_cross_venue_arbitrage(self, results):
        objects = []
        for _, _, _, cases in results:
            for case in cases:
                if hasattr(case, "model_dump"):
                    objects.append(case.model_dump())
                else:
                    objects.append(dict(case))

        lines = [f"🧮 3. Arbitrage case generation ({len(objects)})"]
        if not objects:
            self._post("\n".join(lines))
            return
        for idx, obj in enumerate(objects, 1):
            lines.append(
                f"{idx}. {obj.get('case_name','')} | edge_net={obj.get('edge_net',0):.4f} "
                f"| K: {obj.get('kalshi_action','')} | P: {obj.get('polymarket_action','')}"
            )
        max_len = 3500
        chunk: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk and chunk_len + len(line) + 1 > max_len:
                self._post("\n".join(chunk))
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            self._post("\n".join(chunk))

    def notify_cross_venue_filters(self, results):
        lines = [f"🧪 4. Filter checks ({len(results)})"]
        if not results:
            self._post("\n".join(lines))
            return
        for idx, entry in enumerate(results, 1):
            case = entry.get("case", {})
            report = entry.get("filter_report", {})
            status = "PASS" if report.get("passed") else "FAIL"
            reason = report.get("fail_reason") or report.get("fail_filter") or ""
            lines.append(
                f"{idx}. {case.get('case_name','')} | {status} | {reason}"
            )
        max_len = 3500
        chunk: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk and chunk_len + len(line) + 1 > max_len:
                self._post("\n".join(chunk))
                chunk = []
                chunk_len = 0
            chunk.append(line)
            chunk_len += len(line) + 1
        if chunk:
            self._post("\n".join(chunk))

    def notify_cross_venue_risk(self, results):
        lines = [f"✅ 5. Risk approval ({len(results)})"]
        for idx, entry in enumerate(results, 1):
            case = entry.get("case", {})
            report = entry.get("filter_report", {})
            if report.get("passed"):
                status = "FAIL"
                reason = "cross-venue execution disabled"
            else:
                status = "FAIL"
                reason = report.get("fail_reason") or report.get("fail_filter") or "filtered"
            lines.append(f"{idx}. {case.get('case_name','')} | {status} | {reason}")
        self._post("\n".join(lines))

    def notify_cross_venue_trade(self, results):
        lines = [f"🧾 6. Paper trade ({len(results)})"]
        for idx, entry in enumerate(results, 1):
            case = entry.get("case", {})
            report = entry.get("filter_report", {})
            if report.get("passed"):
                status = "FAIL"
                reason = "cross-venue execution disabled"
            else:
                status = "FAIL"
                reason = report.get("fail_reason") or report.get("fail_filter") or "filtered"
            lines.append(f"{idx}. {case.get('case_name','')} | {status} | {reason}")
        self._post("\n".join(lines))
