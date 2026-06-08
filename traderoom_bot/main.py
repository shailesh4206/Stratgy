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


async def main():
    logger.info("🚀 Starting TradeRoom Bot — Final Version")
    config = Config()

    # Startup diagnostics required by mission: .env + token + chat id + DNS.
    logger.info(f"CWD: {os.getcwd()}")
    logger.info(f"Detected .env: {getattr(config, 'ENV_PATH', 'N/A')}")
    logger.info(
        f"TELEGRAM_TOKEN_LOADED: {getattr(config, 'TELEGRAM_TOKEN_LOADED', False)}"
    )
    logger.info(
        f"TELEGRAM_CHAT_ID_LOADED: {getattr(config, 'TELEGRAM_CHAT_ID_LOADED', False)}"
    )
    # DNS runtime check
    try:
        await _dns_check()
    except Exception:
        logger.warning("DNS check raised an unexpected exception")

    from utils.http_client import HttpClient

    http_client = HttpClient()

    tg = TelegramBot(config, http_client)
    rg = RiskGuard(config)
    funding = FundingRateMonitor(http_client)
    news = NewsFilter(http_client)
    journal = TradeJournal()

    analyzer = MarketAnalyzer(config, http_client)

    engine = SignalEngine(config, analyzer, tg, rg, funding, news, journal)


    # Startup diagnostics (DNS/TOKEN/network).
    try:
        await tg.send_startup()
    except Exception as e:
        logger.error(f"Telegram startup failed (non-fatal): {e}")

    market_data = getattr(analyzer, "data_src", None)

    scan_n = 0
    last_summary = datetime.now().date()

    try:
        while True:
            try:
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

                # Hourly dashboard
                if scan_n % 12 == 0:
                    await tg.send_dashboard(rg.get_dashboard())

                # Daily journal at midnight
                now = datetime.now()
                if now.date() != last_summary and now.hour == 0:
                    await tg.send_journal_summary(journal)
                    last_summary = now.date()

                await asyncio.sleep(config.SCAN_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                logger.warning("KeyboardInterrupt received. Stopping...")
                try:
                    await tg.send_message("🛑 *Bot stopped.*")
                except Exception:
                    pass
                break

            except asyncio.CancelledError:
                # Ensure we still run graceful shutdown in finally.
                raise

            except Exception as e:
                logger.error(f"Error: {e}")
                try:
                    await tg.send_message(f"⚠️ Error: `{e}`\nRestarting in 60s...")
                except Exception:
                    pass
                await asyncio.sleep(60)

    finally:
        # Graceful shutdown (close aiohttp sessions)
        try:
            if market_data is not None:
                await market_data.close()
        except Exception as e:
            logger.error(f"Error closing market_data session: {e}")

        try:
            await tg.close()
        except Exception as e:
            logger.error(f"Error closing telegram session: {e}")

        # Close shared HttpClient
        try:
            await http_client.close()
        except Exception as e:
            logger.error(f"Error closing http_client session: {e}")

        # funding/news/market_data close() are no-ops after refactor



if __name__ == "__main__":
    asyncio.run(main())

