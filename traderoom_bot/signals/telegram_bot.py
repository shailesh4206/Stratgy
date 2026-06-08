# signals/telegram_bot.py — HIGH WIN RATE VERSION (Production-hardened)
import asyncio
import random
import aiohttp
from datetime import datetime
from utils.logger import setup_logger, sanitize_text

logger = setup_logger("telegram")


def _escape_markdown_v2(text: str) -> str:
    # Telegram MarkdownV2 special chars: _ * [ ] ( ) ~ ` > # + - = | { } . !
    if text is None:
        return ""
    s = str(text)
    for ch in ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        s = s.replace(ch, f"\\{ch}")
    return s


class TelegramBot:

    def __init__(self, config, http_client):
        self.config = config
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base = f"https://api.telegram.org/bot{self.token}"

        self._http = http_client
        self._timeout = aiohttp.ClientTimeout(total=15)
        self._max_retries = 5



    async def close(self) -> None:
        # Shared HttpClient is closed by main().
        return


    async def send_message(self, text, parse_mode="Markdown") -> bool:
        """Crash-proof Telegram sender.

        Returns False on any failure; never raises.
        """
        try:
            if not self.token or self.token == "YOUR_TOKEN_HERE":
                logger.error(
                    "Telegram token missing/placeholder. Set TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN in .env"
                )
                return False
            if not self.chat_id or self.chat_id == "YOUR_CHAT_ID_HERE":
                logger.error(
                    "Telegram chat_id missing/placeholder. Set TELEGRAM_CHAT_ID in .env"
                )
                return False


            # Use legacy Markdown to avoid strict escaping rules breaking formatting
            safe_text = str(text) if text is not None else ""
            if parse_mode == "MarkdownV2":
                safe_text = _escape_markdown_v2(safe_text)

            payload = {
                "chat_id": str(self.chat_id),
                "text": safe_text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }



            # Defensive validation: Telegram rejects empty/whitespace-only text.
            if safe_text is None:
                logger.error("Telegram send_message: message text is None")
                return False
            if isinstance(safe_text, str):
                _trim = safe_text.strip()
                if not _trim:
                    logger.error(
                        "Telegram send_message: message text is empty/whitespace. len={} source={}".format(
                            len(safe_text), type(text).__name__
                        )
                    )
                    return False
            else:
                # Extremely defensive
                logger.error(f"Telegram send_message: message text not str type={type(safe_text)}")
                return False

            for attempt in range(self._max_retries):
                try:
                    # NOTE: Telegram expects form-urlencoded or JSON. We send JSON payload.
                    # HttpClient.request_json doesn't support json body, so we must send via params.
                    # Workaround: encode payload into params for aiohttp request.
                    resp_json = await self._http.request_json(
                        f"{self.base}/sendMessage",
                        params={
                            k: ("true" if v is True else "false" if v is False else v)
                            for k, v in payload.items()
                        },
                        method="POST",


                        timeout=self._timeout,
                        headers=None,
                        expected_status=(200,),
                        log_ctx=f"telegram/sendMessage attempt={attempt+1}",
                    )
                    if not resp_json:
                        return False
                    ok = bool(resp_json.get("ok", False))
                    if not ok:
                        logger.error(f"Telegram sendMessage rejected: resp={resp_json}")
                    return ok


                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    wait_s = (2 ** attempt) + random.random()
                    logger.warning(
                        f"Telegram send attempt {attempt+1}/{self._max_retries} failed: {e}. Backoff {wait_s:.1f}s"
                    )
                    await asyncio.sleep(wait_s)

            return False
        except Exception as e:
            # Telegram must NEVER crash the bot.
            logger.error(f"Telegram send_message crashed: {e}")
            return False



    def _bar(self, pct, w=10):
        pct=max(0,min(100,pct)); f=int(pct/(100/w))
        return "█"*f+"░"*(w-f)

    def _danger(self, pct):
        # Use text instead of emoji to avoid Markdown parsing issues.
        if pct >= 75:
            return "[RED]"
        if pct >= 50:
            return "[YELLOW]"
        return "[GREEN]"


    def _format_signal(self, sig):
        # Defensive formatting: Telegram must never crash the bot.
        try:
            lvl = sig.get("levels", {})
            tr  = sig.get("tr", {})
            d   = sig.get("direction", "NONE")
            sym = sig.get("symbol", "UNKNOWN")
        except Exception:
            return "Signal formatting error — invalid signal payload"

        px = sig.get("price", 0)
        arrow  ="🟢 LONG" if d=="LONG" else ("🔴 SHORT" if d=="SHORT" else "⚪ NONE")
        
        # Helper to get value or default
        def safe_get(d, key, fmt=None, default="—"):
            val = d.get(key)
            if val is None:
                return default
            if fmt and isinstance(val, (int, float)):
                try:
                    return fmt.format(val)
                except:
                    return str(val)
            return str(val)

        def safe_get_dual(d, key):
            val = d.get(key)
            if val is None:
                return "—"
            try:
                usd = float(val)
                inr = usd * 84
                return f"${usd:,.2f} (₹{inr:,.2f})"
            except:
                return str(val)

        # Build Reasons (max 5 lines)
        reasons = sig.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []
        
        reason_lines = []
        for i in range(5):
            if i < len(reasons):
                reason_lines.append(f"- {reasons[i]}")
            else:
                reason_lines.append("- —")
        
        reasons_text = "\n".join(reason_lines)

        timestamp_str = sig.get('timestamp')
        if hasattr(timestamp_str, 'strftime'):
            timestamp_str = timestamp_str.strftime('%d %b %Y  %H:%M')

        msg = f"""🚀 SIGNAL — {sym}
{arrow}

────────────────────────────────────────
ENTRY BLOCK:
Live Price: ${px:,.2f} (₹{px*84:,.2f})
Entry Zone: {safe_get_dual(lvl, 'entry_low')} → {safe_get_dual(lvl, 'entry_high')}
Stop Loss: {safe_get_dual(lvl, 'stop_loss')}
Take Profit:
TP1: {safe_get_dual(lvl, 'target_1')}
TP2: {safe_get_dual(lvl, 'target_2')}
TP3: {safe_get_dual(lvl, 'target_3')}

Risk/Reward: 1:{safe_get(lvl, 'risk_reward', '{:.1f}')}

────────────────────────────────────────
MARKET CONFIRMATION:
ADX: {safe_get(sig, 'adx', '{:.0f}')} ({safe_get(sig, 'adx_strength')})
OBV: {safe_get(sig, 'obv_signal')}
FIB LEVEL: {safe_get(sig, 'fib_level')}
CANDLE: {safe_get(sig, 'candle')}
REGIME: {safe_get(sig, 'regime')}
SESSION: {safe_get(sig, 'session')}

────────────────────────────────────────
RISK METRICS:
RSI: {safe_get(sig, 'rsi', '{:.0f}')}
Volume: {safe_get(sig, 'rel_volume', '{:.1f}')}x
Funding Rate: {safe_get(sig, 'funding_rate', '{:.4f}')}% ({safe_get(sig, 'funding_bias')})

────────────────────────────────────────
TRADE STATUS:
Stage: {safe_get(tr, 'stage')}
Confidence: {safe_get(sig, 'confidence')}%
Quality: {safe_get(sig, 'quality')}

────────────────────────────────────────
ACCOUNT STATUS:
Daily PnL: {safe_get(tr, 'daily_pct', '{:.0f}')}%
Total PnL: {safe_get(tr, 'total_pct', '{:.0f}')}%
Trades Today: {safe_get(tr, 'trades_today')}

────────────────────────────────────────
REASONS (max 5 lines):
{reasons_text}

────────────────────────────────────────
FOOTER:
⚠️ Signal only — not financial advice
⚠️ Risk max per trade: $15 (₹1260)
🕐 Timestamp: {timestamp_str or '—'}"""
        return msg

    async def send_signal(self, sig):
        return await self.send_message(self._format_signal(sig))

    async def send_no_signal(self, n=0):
        if n%6==0 and n>0:
            await self.send_message(
                f"⏳ *Scan #{n}* — No quality setup.\n"
                f"_ADX/OBV/Regime filters protecting your account._\n"
                f"🕐 `{datetime.now().strftime('%H:%M')} IST`")

    async def send_news_pause(self, nr):
        alerts="\n".join(nr["news"].get("alerts",[])[:3]) or "High-impact event"
        await self.send_message(
            f"🚨 *TRADING PAUSED*\n━━━━━━━━━━━━━━━━\n{alerts}\n\n"
            f"⛔ No signals until news passes.\n"
            f"🕐 `{datetime.now().strftime('%H:%M')} IST`")

    async def send_rule_block(self, reason):
        await self.send_message(f"🛑 *BLOCKED*\n━━━━━━━━━━━━\n{reason}")

    async def send_dashboard(self, d):
        pb =self._bar(d["profit_pct"])
        dlb=self._bar(d["daily_loss"]/d["daily_limit"]*100 if d["daily_limit"] else 0)
        tlb=self._bar(d["total_loss"]/d["total_limit"]*100 if d["total_limit"] else 0)
        await self.send_message(f"""
📊 *TRADEROOM DASHBOARD*
━━━━━━━━━━━━━━━━━━━━━━━
Stage: `{d['stage']}` | Balance: `${d['balance']:,} (₹{d['balance']*84:,})`
🎯 `{pb}` `{d['profit_pct']}%` — Need `${d['profit_needed']} (₹{d['profit_needed']*84})`
{self._danger(d['daily_loss']/d['daily_limit']*100 if d['daily_limit'] else 0)} Daily: `{dlb}` `${d['daily_loss']} (₹{d['daily_loss']*84})`/`$100 (₹8400)`
{self._danger(d['total_loss']/d['total_limit']*100 if d['total_limit'] else 0)} Total: `{tlb}` `${d['total_loss']} (₹{d['total_loss']*84})`/`$200 (₹16800)`
📅 Trading days: `{d['trading_days']}`
🕐 `{datetime.now().strftime('%d %b  %H:%M')} IST`
""".strip())

    async def send_journal_summary(self, journal):
        await self.send_message(journal.format_daily_summary())

    async def send_startup(self):
        # Extract information from the original message structure
        timestamp = datetime.now().strftime("%d %b %Y  %H:%M:%S IST")

        msg = f"""
🚀 *TRADEROOM BOT — SYSTEM STARTUP*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bot is live and monitoring the markets for high-probability setups.

⚙️ *SYSTEM CONFIGURATION*
• Mode: `SIGNAL ONLY`
• Risk Per Trade: `$15 (₹1260)`
• Daily Stop Loss: `$80 (₹6720)`
• Total Stop Loss: `$160 (₹13440)`
• Target Win Rate: `55%+`
• Minimum R/R: `1:3`
• Minimum Confidence: `72%`

🕐 *Startup Time:* `{timestamp}`
"""
        await self.send_message(msg.strip())
