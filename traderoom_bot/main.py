#!/usr/bin/env python3
"""VECTORAX TRADEROOM SIGNAL BOT — Final Version"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime

from config.settings import Config
from analysis.market_analyzer import MarketAnalyzer
from analysis.funding_rate import FundingRateMonitor
from analysis.news_filter import NewsFilter
from strategy.signal_engine import SignalEngine
from strategy.risk_guard import RiskGuard
from signals.telegram_bot import TelegramBot
from utils.logger import setup_logger
from utils.journal import TradeJournal

logger = setup_logger("main")


async def _dns_check(host: str = "api.binance.com") -> bool:
    # Quick runtime DNS check to surface resolution issues early.
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None)
        if infos:
            addr = infos[0][4][0]
            logger.info(f"DNS check: {host} -> {addr}")
            return True
    except Exception as e:
        logger.warning(f"DNS resolution failed for {host}: {e}")
    return False


async def run_bot():
    logger.info("🚀 Starting TradeRoom Bot — Final Version")
    config = Config()

    logger.info(f"CWD: {os.getcwd()}")
    logger.info(f"Detected .env: {getattr(config, 'ENV_PATH', 'N/A')}")
    logger.info(f"TELEGRAM_TOKEN_LOADED: {getattr(config, 'TELEGRAM_TOKEN_LOADED', False)}")
    logger.info(f"TELEGRAM_CHAT_ID_LOADED: {getattr(config, 'TELEGRAM_CHAT_ID_LOADED', False)}")

    try:
        await _dns_check()
    except Exception:
        logger.warning("DNS check raised an unexpected exception")

    from utils.http_client import HttpClient

    async with HttpClient() as http_client:
        tg = TelegramBot(config, http_client)
        rg = RiskGuard(config)
        funding = FundingRateMonitor(http_client)
        news = NewsFilter(http_client)
        journal = TradeJournal()
        analyzer = MarketAnalyzer(config, http_client)
        engine = SignalEngine(config, analyzer, tg, rg, funding, news, journal)

        try:
            await tg.send_startup()
        except Exception as e:
            logger.error(f"Telegram startup failed (non-fatal): {e}")

        scan_n = 0
        last_summary = datetime.now().date()

        while True:
            scan_n += 1
            logger.info(f"\n{'=' * 45}")
            logger.info(f"🔍 Scan #{scan_n} — {datetime.now().strftime('%H:%M:%S')}")

            can = rg.can_trade()
            if not can["ok"]:
                logger.warning(f"🛑 {can['reason'][:50]}")
                if scan_n % 6 == 0:
                    await tg.send_rule_block(can["reason"])
            else:
                await engine.run_full_scan()

            if scan_n % 12 == 0:
                await tg.send_dashboard(rg.get_dashboard())

            now = datetime.now()
            if now.date() != last_summary and now.hour == 0:
                await tg.send_journal_summary(journal)
                last_summary = now.date()

            await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)


async def main():
    while True:
        try:
            await run_bot()
        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt received. Stopping bot permanently.")
            break
        except asyncio.CancelledError:
            logger.warning("Task cancelled. Stopping bot permanently.")
            raise
        except Exception as e:
            logger.error(f"CRITICAL WATCHDOG CAUGHT EXCEPTION: {e}")
            logger.info("Restarting bot in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())

