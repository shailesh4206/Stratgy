import asyncio
import sys
sys.path.insert(0, 'traderoom_bot')

from traderoom_bot.config.settings import Config
from traderoom_bot.analysis.market_analyzer import MarketAnalyzer
from traderoom_bot.analysis.funding_rate import FundingRateMonitor
from traderoom_bot.analysis.news_filter import NewsFilter
from traderoom_bot.strategy.signal_engine import SignalEngine
from traderoom_bot.strategy.risk_guard import RiskGuard
from traderoom_bot.utils.http_client import HttpClient
from traderoom_bot.utils.journal import TradeJournal

async def main():
    config = Config()
    http = HttpClient()
    analyzer = MarketAnalyzer(config, http)
    funding = FundingRateMonitor(http)
    news = NewsFilter(http)
    rg = RiskGuard(config)
    journal = TradeJournal()
    engine = SignalEngine(config, analyzer, None, rg, funding, news, journal)
    news_result = await news.check()
    print('NEWS', news_result['session'], 'pause', news_result['should_pause'])
    analyses = await analyzer.analyze_all_pairs(config.PAIRS)
    for sym, analysis in analyses.items():
        sig = await engine.generate(sym, analysis, news_result)
        if sig:
            print('SIGNAL', sig)
        else:
            print('NO_SIGNAL', sym)
    await http.close()

if __name__ == '__main__':
    asyncio.run(main())
