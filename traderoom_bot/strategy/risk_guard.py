# strategy/risk_guard.py
"""
TradeRoom Risk Guardian — Final Version
YOUR limits: $80/day stop, $160 total stop, $15/trade
TR official:  $250/day,    $500 total,     (never reached)
"""
from datetime import datetime
from utils.logger import setup_logger
logger = setup_logger("risk")


class RiskGuard:

    def __init__(self, config):
        self.config           = config
        self.daily_loss       = 0.0
        self.total_loss       = 0.0
        self.total_profit     = 0.0
        self.trades_today     = 0
        self.trading_days     = 0
        self.today_had_trade  = False
        self.last_reset       = datetime.now().date()
        self.balance          = config.ACCOUNT_SIZE
        self.stage            = config.CURRENT_STAGE

    def _daily_reset(self):
        today = datetime.now().date()
        if today != self.last_reset:
            if self.today_had_trade:
                self.trading_days += 1
            self.daily_loss      = 0.0
            self.trades_today    = 0
            self.today_had_trade = False
            self.last_reset      = today
            logger.info("🔄 Daily reset done.")

    def record(self, pnl: float):
        self.today_had_trade = True
        self.trades_today   += 1
        if pnl >= 0:
            self.total_profit += pnl
            self.balance      += pnl
        else:
            self.daily_loss  += abs(pnl)
            self.total_loss  += abs(pnl)
            self.balance     -= abs(pnl)

    def can_trade(self) -> dict:
        self._daily_reset()
        w = []   # warnings

        # ── 1. Your daily stop ($80) ──────────────────────────
        if self.daily_loss >= self.config.MY_DAILY_STOP_AT:
            left = self.config.TR_DAILY_LOSS_LIMIT - self.daily_loss
            return {"ok": False, "reason": (
                f"🛑 YOUR daily limit hit — Lost ${self.daily_loss:.0f} today\n"
                f"Your safe limit: ${self.config.MY_DAILY_STOP_AT} ✅\n"
                f"TradeRoom still has ${left:.0f} room — but bot protects you.\n"
                f"➡️ Stop trading. Resume tomorrow fresh."
            ), "warnings": w}

        if self.daily_loss >= 60:
            w.append(f"⚠️ Daily loss ${self.daily_loss:.0f} — be selective now")

        # ── 2. Your total stop ($160) ─────────────────────────
        if self.total_loss >= self.config.MY_MAX_STOP_AT:
            return {"ok": False, "reason": (
                f"🛑 YOUR total loss limit hit — ${self.total_loss:.0f} total\n"
                f"Your safe limit: ${self.config.MY_MAX_STOP_AT}\n"
                f"TradeRoom limit: ${self.config.TR_MAX_LOSS_LIMIT} — still safe.\n"
                f"➡️ Take a break. Review your trades."
            ), "warnings": w}

        if self.total_loss >= 120:
            w.append(f"🚨 Total loss ${self.total_loss:.0f} — high caution zone")

        # ── 3. Max trades today ───────────────────────────────
        if self.trades_today >= self.config.MAX_TRADES_PER_DAY:
            return {"ok": False, "reason":
                f"🛑 {self.config.MAX_TRADES_PER_DAY} trades done today. Wait for tomorrow.",
                "warnings": w}

        return {"ok": True, "reason": "✅ All clear", "warnings": w}


    def validate_signal(self, signal: dict):
        check = self.can_trade()
        if not check["ok"]:
            logger.warning(f"Signal blocked: {check['reason'][:50]}")
            return None

        # Stage-based target
        if self.stage == "STAGE1": target = self.config.S1_PROFIT_TARGET
        elif self.stage == "STAGE2": target = self.config.S2_PROFIT_TARGET
        else: target = 99999

        entry    = signal["levels"]["entry_low"]
        sl       = signal["levels"]["stop_loss"]
        risk_pts = abs(entry - sl)
        if risk_pts <= 0: return None

        units       = self.config.RISK_PER_TRADE_USD / risk_pts
        profit_est  = abs(signal["levels"]["target_2"] - entry) * units

        profit_pct  = min(100, self.total_profit / target * 100) if target else 0
        daily_pct   = self.daily_loss / self.config.MY_DAILY_LOSS_LIMIT * 100
        total_pct   = self.total_loss / self.config.MY_MAX_LOSS_LIMIT * 100

        signal["tr"] = {
            "stage":           self.stage,
            "risk_usd":        self.config.RISK_PER_TRADE_USD,
            "profit_est":      round(profit_est, 2),
            "units":           round(units, 6),
            "daily_loss":      round(self.daily_loss, 2),
            "daily_remaining": round(self.config.MY_DAILY_LOSS_LIMIT - self.daily_loss, 2),
            "daily_pct":       round(daily_pct, 1),
            "total_loss":      round(self.total_loss, 2),
            "total_remaining": round(self.config.MY_MAX_LOSS_LIMIT - self.total_loss, 2),
            "total_pct":       round(total_pct, 1),
            "profit_made":     round(self.total_profit, 2),
            "profit_needed":   round(max(0, target - self.total_profit), 2),
            "profit_pct":      round(profit_pct, 1),
            "target":          target,
            "trading_days":    self.trading_days,
            "trades_today":    self.trades_today + 1,
            "warnings":        check["warnings"],
        }
        return signal

    def get_dashboard(self):
        if self.stage == "STAGE1": target = self.config.S1_PROFIT_TARGET
        elif self.stage == "STAGE2": target = self.config.S2_PROFIT_TARGET
        else: target = 99999
        return {
            "stage":         self.stage,
            "balance":       round(self.balance, 2),
            "profit_made":   round(self.total_profit, 2),
            "profit_needed": round(max(0, target - self.total_profit), 2),
            "profit_pct":    round(min(100, self.total_profit / target * 100) if target else 0, 1),
            "target":        target,
            "daily_loss":    round(self.daily_loss, 2),
            "daily_limit":   self.config.MY_DAILY_LOSS_LIMIT,
            "daily_stop":    self.config.MY_DAILY_STOP_AT,
            "total_loss":    round(self.total_loss, 2),
            "total_limit":   self.config.MY_MAX_LOSS_LIMIT,
            "total_stop":    self.config.MY_MAX_STOP_AT,
            "trading_days":  self.trading_days,
            "trades_today":  self.trades_today,
        }
