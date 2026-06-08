# analysis/market_data.py
"""Market Data Fetcher

Fetches OHLCV / ticker / orderbook data from Binance.

Evidence-based production goals (per your logs):
- If OS DNS tools succeed (nslookup/ping/curl), remove/avoid any custom aiohttp DNS resolver.
- Use a single shared aiohttp session with an explicit TCPConnector.
- Use timeouts + retries.
- Return None on failures (never crash caller).
"""

import asyncio
from typing import Optional


import aiohttp
import pandas as pd

from utils.http_client import HttpClient
from utils.logger import setup_logger

logger = setup_logger("market_data")


class MarketData:
    BASE_URL = "https://api.binance.com/api/v3"
    RETRY_COUNT = 3

    def __init__(self, http_client: HttpClient):
        self._http = http_client




    async def _request_json(self, url: str, *, params: dict) -> Optional[dict]:
        # Delegate HTTP + connector policy + retries to shared HttpClient.
        return await self._http.request_json(
            url,
            params=params,
            method="GET",
            timeout=aiohttp.ClientTimeout(total=20),
            expected_status=(200,),
            log_ctx=f"market_data/binance {url}",
        )


    async def get_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> Optional[pd.DataFrame]:

        url = f"{self.BASE_URL}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        data = await self._request_json(url, params=params)
        if not data:
            return None

        try:
            df = pd.DataFrame(
                data,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )

            for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
            df.set_index("timestamp", inplace=True)

            return df
        except Exception as e:
            logger.error(f"Error parsing klines for {symbol} {interval}: {e}")
            return None

    async def get_ticker(self, symbol: str) -> Optional[dict]:
        url = f"{self.BASE_URL}/ticker/24hr"
        params = {"symbol": symbol}

        data = await self._request_json(url, params=params)
        if not data:
            return None

        try:
            return {
                "symbol": symbol,
                "price": float(data["lastPrice"]),
                "change_pct": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "volume_24h": float(data["volume"]),
                "quote_volume_24h": float(data["quoteVolume"]),
            }
        except Exception as e:
            logger.error(f"Error parsing ticker for {symbol}: {e}")
            return None

    async def get_orderbook(self, symbol: str, limit: int = 20) -> Optional[dict]:
        url = f"{self.BASE_URL}/depth"
        params = {"symbol": symbol, "limit": limit}

        data = await self._request_json(url, params=params)
        if not data:
            return None

        try:
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])]
            if not bids or not asks:
                return None

            total_bid_vol = sum(q for _, q in bids)
            total_ask_vol = sum(q for _, q in asks)
            if (total_bid_vol + total_ask_vol) <= 0:
                return None

            return {
                "bids": bids,
                "asks": asks,
                "bid_wall": max(bids, key=lambda x: x[1]) if bids else None,
                "ask_wall": max(asks, key=lambda x: x[1]) if asks else None,
                "buy_pressure": total_bid_vol / (total_bid_vol + total_ask_vol) * 100,
                "sell_pressure": total_ask_vol / (total_bid_vol + total_ask_vol) * 100,
            }
        except Exception as e:
            logger.error(f"Error parsing orderbook for {symbol}: {e}")
            return None

    async def close(self):
        # Shared HttpClient is owned by main().
        return



