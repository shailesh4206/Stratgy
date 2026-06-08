# analysis/market_analyzer.py
"""
Master Market Analyzer
Combines technical indicators + SMC analysis for each pair.
"""

import asyncio
from analysis.market_data import MarketData

from analysis.indicators import Indicators
from analysis.smc_analyzer import SMCAnalyzer
from utils.logger import setup_logger

logger = setup_logger("market_analyzer")


class MarketAnalyzer:

    def __init__(self, config, http_client=None):
        self.config = config
        # MarketData must use shared HttpClient (connector policy).
        self.data_src = MarketData(http_client) if http_client is not None else MarketData()



    async def analyze_pair(self, symbol: str) -> dict:
        """Full analysis for a single pair across multiple timeframes."""
        logger.info(f"📈 Analyzing {symbol}...")

        try:
            # Fetch data for multiple timeframes concurrently
            tasks = [
                self.data_src.get_klines(symbol, "1d",  200),
                self.data_src.get_klines(symbol, "4h",  200),
                self.data_src.get_klines(symbol, "1h",  100),
                self.data_src.get_klines(symbol, "15m", 100),
                self.data_src.get_ticker(symbol),
                self.data_src.get_orderbook(symbol),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            df_1d, df_4h, df_1h, df_15m, ticker, orderbook = results

            if df_1d is None or df_4h is None:
                logger.warning(f"⚠️ Failed to fetch data for {symbol}")
                return None

            # ── Indicators ──────────────────────────────────────
            ind_1d  = Indicators.compute_all(df_1d,  self.config) if df_1d  is not None else None
            ind_4h  = Indicators.compute_all(df_4h,  self.config) if df_4h  is not None else None
            ind_1h  = Indicators.compute_all(df_1h,  self.config) if df_1h  is not None else None
            ind_15m = Indicators.compute_all(df_15m, self.config) if df_15m is not None else None

            # ── SMC Analysis (4H + 1H) ──────────────────────────
            ms_4h    = SMCAnalyzer.detect_market_structure(df_4h)
            ms_1h    = SMCAnalyzer.detect_market_structure(df_1h) if df_1h is not None else {}
            obs      = SMCAnalyzer.detect_order_blocks(df_4h)
            fvgs     = SMCAnalyzer.detect_fvg(df_4h)
            liq      = SMCAnalyzer.detect_liquidity(df_4h)
            bos      = SMCAnalyzer.detect_bos_choch(df_4h)

            current_price = ticker["price"] if ticker else float(df_4h["close"].iloc[-1])

            return {
                "symbol":        symbol,
                "current_price": current_price,
                "ticker":        ticker,
                "orderbook":     orderbook,
                "timeframes": {
                    "1d":  {"df": df_1d,  "indicators": ind_1d},
                    "4h":  {"df": df_4h,  "indicators": ind_4h},
                    "1h":  {"df": df_1h,  "indicators": ind_1h},
                    "15m": {"df": df_15m, "indicators": ind_15m},
                },
                "smc": {
                    "market_structure_4h": ms_4h,
                    "market_structure_1h": ms_1h,
                    "order_blocks":        obs,
                    "fvg":                 fvgs,
                    "liquidity":           liq,
                    "bos_choch":           bos,
                },
                "ind_4h": ind_4h["latest"] if ind_4h else {},
                "ind_1h": ind_1h["latest"] if ind_1h else {},
                "ind_1d": ind_1d["latest"] if ind_1d else {},
            }

        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None

    async def analyze_all_pairs(self, pairs: list) -> dict:
        """Analyze all pairs concurrently."""
        tasks = [self.analyze_pair(symbol) for symbol in pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        analysis = {}
        for symbol, result in zip(pairs, results):
            if isinstance(result, Exception):
                logger.error(f"Exception for {symbol}: {result}")
            elif result is not None:
                analysis[symbol] = result

        return analysis
