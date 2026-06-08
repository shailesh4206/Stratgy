# analysis/funding_rate.py
"""
Funding Rate + Open Interest Monitor
Fetches live derivatives data from Binance Futures public API.
No API key needed — completely free.

Why this matters for $5K account:
- Funding rate > +0.1%  → Longs overloaded → SHORT bias (contrarian)
- Funding rate < -0.1%  → Shorts overloaded → LONG bias (contrarian)
- OI rising + price rising → Strong bullish momentum
- OI falling + price rising → Weak move, likely reversal
"""

import asyncio
from datetime import datetime
from typing import Optional

import aiohttp

from utils.http_client import HttpClient
from utils.logger import setup_logger


logger = setup_logger("funding")

FAPI = "https://fapi.binance.com/fapi/v1"


class FundingRateMonitor:

    def __init__(self, http_client: HttpClient):
        self._http = http_client
        self._cache: dict[str, dict] = {}  # symbol → {data, timestamp}
        self.CACHE_SECONDS = 300  # Cache 5 minutes


    def _is_cached(self, symbol):
        if symbol not in self._cache:
            return False
        age = (datetime.now() - self._cache[symbol]["ts"]).seconds
        return age < self.CACHE_SECONDS

    async def get_funding_rate(self, symbol: str) -> dict:
        """Get current funding rate from Binance Futures."""
        if self._is_cached(symbol):
            return self._cache[symbol]["data"]

        url = f"{FAPI}/premiumIndex"
        # Shared HttpClient already provides retries/backoff + connector policy.
        raw = await self._http.request_json(
            url,
            params={"symbol": symbol},
            method="GET",
            timeout=aiohttp.ClientTimeout(total=10),
            expected_status=(200,),
            log_ctx=f"funding/premiumIndex symbol={symbol}",
        )
        if not raw:
            return self._default(symbol)

        try:
            fr = float(raw.get("lastFundingRate", 0))
            mark_price = float(raw.get("markPrice", 0))
            fr_pct = fr * 100

            # Interpret signal
            if fr > 0.001:
                signal = "EXTREME_LONGS"
                bias = "SHORT"  # Too many longs → market likely drops
                quality = -2
                note = f"Extreme longs ({fr_pct:.4f}%) — short bias"
            elif fr > 0.0003:
                signal = "BULLISH_BIAS"
                bias = "NEUTRAL"
                quality = -1
                note = f"Slight long bias ({fr_pct:.4f}%)"
            elif fr < -0.001:
                signal = "EXTREME_SHORTS"
                bias = "LONG"  # Too many shorts → likely squeeze up
                quality = 2
                note = f"Extreme shorts ({fr_pct:.4f}%) — long bias"
            elif fr < -0.0003:
                signal = "BEARISH_BIAS"
                bias = "NEUTRAL"
                quality = 1
                note = f"Slight short bias ({fr_pct:.4f}%)"
            else:
                signal = "NEUTRAL"
                bias = "NEUTRAL"
                quality = 0
                note = f"Neutral funding ({fr_pct:.4f}%)"

            result = {
                "symbol": symbol,
                "rate": fr,
                "rate_pct": round(fr_pct, 4),
                "mark_price": mark_price,
                "signal": signal,
                "bias": bias,
                "quality": quality,
                "note": note,
                "is_extreme": abs(fr) > 0.001,
            }
            self._cache[symbol] = {"data": result, "ts": datetime.now()}
            logger.info(f"  💰 Funding {symbol}: {fr_pct:.4f}% → {signal}")
            return result
        except Exception as e:
            logger.warning(f"Funding rate parse error for {symbol}: {e}")
            return self._default(symbol)


    async def get_open_interest(self, symbol: str) -> dict:
        """Get Open Interest trend from Binance."""
        try:
            cur_raw = await self._http.request_json(
                f"{FAPI}/openInterest",
                params={"symbol": symbol},
                method="GET",
                timeout=aiohttp.ClientTimeout(total=10),
                expected_status=(200,),
                log_ctx=f"funding/openInterest symbol={symbol}",
            )
            if not cur_raw:
                return None
            current_oi = float(cur_raw.get("openInterest", 0))

            # Binance Futures open interest history.
            # Your logs show /fapi/v1/openInterestHist returns 404.
            # Use the currently supported namespace: /fapi/v1/futures/data/openInterestHist
            # (and keep additional ordered fallbacks).
            hist = None
            hist_attempts = [
                # Newer supported namespace (commonly used by Binance Futures):
                ("funding/openInterestHist(futures-data)",
                 f"https://fapi.binance.com/futures/data/openInterestHist",
                 {"symbol": symbol, "period": "1h", "limit": 5}),
                # Some accounts accept fewer params:
                ("funding/openInterestHist(futures-data-no-limit)",
                 f"https://fapi.binance.com/futures/data/openInterestHist",
                 {"symbol": symbol, "period": "1h"}),
                # Last-resort legacy path (may still work on some environments):
                ("funding/openInterestHist(legacy)",
                 f"{FAPI}/openInterestHist",
                 {"symbol": symbol, "period": "1h", "limit": 5}),
                ("funding/openInterestHist(legacy-no-limit)",
                 f"{FAPI}/openInterestHist",
                 {"symbol": symbol, "period": "1h"}),
            ]

            for log_ctx, url, params in hist_attempts:
                hist = await self._http.request_json(
                    url,
                    params=params,
                    method="GET",
                    timeout=aiohttp.ClientTimeout(total=10),
                    expected_status=(200,),
                    log_ctx=log_ctx + f" symbol={symbol}",
                )
                if hist is not None:
                    break

            # If history is unavailable (404/5xx), keep business logic non-blocking.
            trend = "NEUTRAL"
            change_pct = 0.0
            if isinstance(hist, list) and len(hist) >= 2:
                old = float(hist[0].get("sumOpenInterest", 0))
                new = float(hist[-1].get("sumOpenInterest", 0))
                change_pct = ((new - old) / old * 100) if old > 0 else 0
                if change_pct > 5:
                    trend = "RISING_FAST"
                elif change_pct > 2:
                    trend = "RISING"
                elif change_pct < -5:
                    trend = "FALLING_FAST"
                elif change_pct < -2:
                    trend = "FALLING"

            # Return OI trend only if we successfully computed it from history.
            oi_trend_available = hist is not None

            return {
                "symbol": symbol,
                "oi": current_oi,
                "trend": trend if oi_trend_available else "NEUTRAL",
                "change_pct": round(change_pct, 2) if oi_trend_available else 0.0,
            }

        except Exception as e:
            logger.warning(f"OI error for {symbol}: {e}")
            return None


    async def get_all(self, symbol: str) -> dict:
        """Fetch funding rate + OI together."""
        fr, oi = await asyncio.gather(
            self.get_funding_rate(symbol),
            self.get_open_interest(symbol),
            return_exceptions=True
        )
        return {
            "funding":       fr if not isinstance(fr, Exception) else self._default(symbol),
            "open_interest": oi if not isinstance(oi, Exception) else None,
        }





    def _default(self, symbol):
        return {
            "symbol": symbol, "rate": 0, "rate_pct": 0,
            "mark_price": 0, "signal": "UNKNOWN", "bias": "NEUTRAL",
            "quality": 0, "note": "Data unavailable", "is_extreme": False,
        }

    async def close(self):
        # Shared HttpClient is owned by main().
        return

