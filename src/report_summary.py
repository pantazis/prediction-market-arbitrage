from pathlib import Path
from typing import Union, List, Dict
import csv


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    """Read CSV rows from path and return list of dicts.

    If the file lacks a header, infer the expected paper trades headers.
    """
    rows: List[Dict[str, str]] = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8") as f:
        # Sniff dialect for robustness
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except Exception:
            dialect = csv.excel
        reader = csv.reader(f, dialect)
        try:
            header = next(reader)
        except StopIteration:
            return rows
        # If first row looks like data (timestamp format), provide default headers for paper trades
        default_trade_headers = [
            "timestamp",
            "market_id",
            "outcome_id",
            "side",
            "amount",
            "price",
            "fees",
            "slippage",
            "realized_pnl",
        ]
        def is_header_like(cols: List[str]) -> bool:
            # Heuristic: headers are alphabetic/underscore; data rows often start with ISO timestamp
            # Accept if all entries contain any lowercase/underscore and not starting with a digit.
            for c in cols:
                if not c:
                    return False
                if c[0].isdigit():
                    return False
            return True

        if not is_header_like(header) and len(header) == len(default_trade_headers):
            # Treat the first row as data and use default headers
            # Rewind and rebuild reader
            f.seek(0)
            reader = csv.reader(f, dialect)
            for row in reader:
                rows.append({h: v for h, v in zip(default_trade_headers, row)})
            return rows
        # Normal header case
        for row in reader:
            rows.append({h: v for h, v in zip(header, row)})
    return rows


def generate_reports_summary(reports_dir: Union[str, Path] = "reports") -> str:
    """Read all known report files and return a human-readable summary.

    Includes:
    - live_summary.csv: iteration, markets, detected, approved, approval%, status, hashes
    - paper_trades.csv: timestamp, market_id, outcome_id, side, amount, price, fees, slippage, realized_pnl
    """
    rdir = Path(reports_dir)
    parts: List[str] = []

    # Live summary
    live_path = rdir / "live_summary.csv"
    live_rows = _read_csv_rows(live_path)
    if live_rows:
        parts.append("Live Summary:")
        for row in live_rows:
            ts = row.get("READABLE_TIME") or row.get("TIMESTAMP") or "?"
            iteration = row.get("ITERATION", "?")
            markets = row.get("MARKETS", "?")
            markets_delta = row.get("MARKETS_Δ", row.get("MARKETS_?", ""))
            detected = row.get("DETECTED", "?")
            detected_delta = row.get("DETECTED_Δ", "")
            approved = row.get("APPROVED", "?")
            approved_delta = row.get("APPROVED_Δ", "")
            approval_pct = row.get("APPROVAL%", "?")
            status = row.get("STATUS", "?")
            mhash = row.get("MARKET_HASH", "")
            ohash = row.get("OPP_HASH", "")
            parts.append(
                f"- Iteration {iteration} at {ts}: markets={markets}{(' ' + markets_delta) if markets_delta else ''} "
                f"detected={detected}{(' ' + detected_delta) if detected_delta else ''} "
                f"approved={approved}{(' ' + approved_delta) if approved_delta else ''} "
                f"approval={approval_pct} status={status} hashes=[market:{mhash}, opp:{ohash}]"
            )

    # Paper trades
    trades_path = rdir / "paper_trades.csv"
    trade_rows = _read_csv_rows(trades_path)
    if trade_rows:
        parts.append("Paper Trades:")
        for row in trade_rows:
            ts = row.get("timestamp", row.get("TIMESTAMP", "?"))
            market_id = row.get("market_id", "?")
            outcome_id = row.get("outcome_id", "?")
            side = row.get("side", "?")
            amount = row.get("amount", "?")
            price = row.get("price", "?")
            fees = row.get("fees", row.get("fee", ""))
            slippage = row.get("slippage", "")
            pnl = row.get("realized_pnl", row.get("pnl", ""))
            parts.append(
                f"- {ts} market={market_id} outcome={outcome_id} {side} {amount}@{price} "
                f"fees={fees} slippage={slippage} pnl={pnl}"
            )

    # Any other files can be added here in the future.

    if not parts:
        return f"No report files found in {rdir}"
    return "\n".join(parts)
