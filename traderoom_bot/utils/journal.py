# utils/journal.py
"""
Trade Journal
Tracks every signal sent → result → P&L
Saves to JSON file locally.
Sends daily summary to Telegram.
"""

import json
import os
from datetime import datetime, date
from utils.logger import setup_logger

logger = setup_logger("journal")

JOURNAL_FILE = "logs/trade_journal.json"


class TradeJournal:

    def __init__(self):
        os.makedirs("logs", exist_ok=True)
        self.entries = self._load()

    def _load(self) -> list:
        if os.path.exists(JOURNAL_FILE):
            try:
                with open(JOURNAL_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save(self):
        with open(JOURNAL_FILE, "w") as f:
            json.dump(self.entries[-500:], f, indent=2)  # Keep last 500

    def log_signal(self, signal: dict) -> str:
        """Log a signal when it's sent. Returns trade ID."""
        trade_id = f"TR{datetime.now().strftime('%m%d%H%M%S')}"
        entry = {
            "id":         trade_id,
            "date":       datetime.now().strftime("%Y-%m-%d"),
            "time":       datetime.now().strftime("%H:%M:%S"),
            "symbol":     signal["symbol"],
            "direction":  signal["direction"],
            "confidence": signal["confidence"],
            "quality":    signal["quality"],
            "entry_low":  signal["levels"]["entry_low"],
            "entry_high": signal["levels"]["entry_high"],
            "stop_loss":  signal["levels"]["stop_loss"],
            "target_1":   signal["levels"]["target_1"],
            "target_2":   signal["levels"]["target_2"],
            "rr":         signal["levels"]["risk_reward"],
            "risk_usd":   signal["traderoom"]["risk_usd"],
            "funding_bias": signal.get("funding_bias", "NEUTRAL"),
            "session":    signal.get("session", "UNKNOWN"),
            "news_ok":    signal.get("news_ok", True),
            # To be filled after trade
            "status":     "OPEN",      # OPEN / WIN / LOSS / SKIPPED / TIMEOUT
            "exit_price": None,
            "pnl_usd":    None,
            "notes":      "",
        }
        self.entries.append(entry)
        self._save()
        logger.info(f"📝 Signal logged: {trade_id} — {signal['symbol']} {signal['direction']}")
        return trade_id

    def update_result(self, trade_id: str, status: str,
                      exit_price: float = None, pnl_usd: float = None, notes: str = ""):
        """Update trade result after it closes."""
        for entry in self.entries:
            if entry["id"] == trade_id:
                entry["status"]     = status
                entry["exit_price"] = exit_price
                entry["pnl_usd"]    = pnl_usd
                entry["notes"]      = notes
                entry["closed_at"]  = datetime.now().strftime("%H:%M:%S")
                self._save()
                logger.info(f"✅ Trade {trade_id} updated: {status} | P&L: ${pnl_usd}")
                return True
        return False

    def get_stats(self, days: int = 30) -> dict:
        """Calculate performance stats for last N days."""
        cutoff = datetime.now().date().isoformat()

        # Filter recent closed trades
        closed = [
            e for e in self.entries
            if e["status"] in ["WIN", "LOSS", "TIMEOUT"]
            and e.get("pnl_usd") is not None
        ]

        if not closed:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0, "total_pnl": 0,
                "avg_win": 0, "avg_loss": 0,
                "best": 0, "worst": 0,
                "profit_factor": 0,
            }

        wins   = [e for e in closed if e["status"] == "WIN"]
        losses = [e for e in closed if e["status"] == "LOSS"]
        pnls   = [e["pnl_usd"] for e in closed]

        win_pnls  = [e["pnl_usd"] for e in wins]
        loss_pnls = [e["pnl_usd"] for e in losses]

        gross_profit = sum(win_pnls) if win_pnls else 0
        gross_loss   = abs(sum(loss_pnls)) if loss_pnls else 1

        return {
            "total":          len(closed),
            "wins":           len(wins),
            "losses":         len(losses),
            "win_rate":       round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "total_pnl":      round(sum(pnls), 2),
            "avg_win":        round(sum(win_pnls) / len(wins), 2) if wins else 0,
            "avg_loss":       round(sum(loss_pnls) / len(losses), 2) if losses else 0,
            "best":           round(max(pnls), 2) if pnls else 0,
            "worst":          round(min(pnls), 2) if pnls else 0,
            "profit_factor":  round(gross_profit / gross_loss, 2),
            "open_trades":    len([e for e in self.entries if e["status"] == "OPEN"]),
        }

    def get_today(self) -> list:
        """Get today's signals."""
        today = datetime.now().strftime("%Y-%m-%d")
        return [e for e in self.entries if e["date"] == today]

    def format_daily_summary(self) -> str:
        """Format today's performance for Telegram."""
        today_trades = self.get_today()
        stats        = self.get_stats()

        if not today_trades:
            return "📋 *No trades today.*"

        lines = [
            "📋 *DAILY TRADE JOURNAL*",
            f"━━━━━━━━━━━━━━━━━━━━━━━",
            f"Date: `{datetime.now().strftime('%d %b %Y')}`",
            f"Signals today: `{len(today_trades)}`",
            "",
        ]

        for t in today_trades:
            icon = {"WIN": "✅", "LOSS": "❌", "OPEN": "🔓", "SKIPPED": "⏭️", "TIMEOUT": "⏳"}.get(t["status"], "❓")
            pnl  = f"${t['pnl_usd']:+.2f}" if t["pnl_usd"] is not None else "pending"
            lines.append(
                f"{icon} `{t['id']}` {t['symbol']} {t['direction']}\n"
                f"   Entry: `${t['entry_low']:,}` | {pnl}"
            )

        lines += [
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━",
            f"*Overall Stats ({stats['total']} trades)*",
            f"Win Rate:  `{stats['win_rate']}%`",
            f"Total P&L: `${stats['total_pnl']:+.2f}`",
            f"Profit Factor: `{stats['profit_factor']}x`",
        ]

        return "\n".join(lines)

    def format_open_trades(self) -> str:
        """Show currently open (pending) signals."""
        open_trades = [e for e in self.entries if e["status"] == "OPEN"]
        if not open_trades:
            return "🔓 No open signals right now."

        lines = ["🔓 *OPEN SIGNALS*", "━━━━━━━━━━━━━━━━"]
        for t in open_trades:
            lines.append(
                f"• `{t['id']}` — {t['symbol']} {t['direction']}\n"
                f"  Entry: `${t['entry_low']:,}–${t['entry_high']:,}`\n"
                f"  SL: `${t['stop_loss']:,}` | TP2: `${t['target_2']:,}`\n"
                f"  Time: `{t['time']}`"
            )
        return "\n".join(lines)
