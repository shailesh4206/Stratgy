# analysis/news_filter.py
"""
News Filter — Auto-pause before high-impact events
Two layers:
  1. CryptoCompare API  → live crypto news sentiment
  2. Keyword detection  → FOMC, CPI, Fed, SEC, hack, etc.

TradeRoom restricts news trading — this module enforces that.
For $5K account: ONE bad news trade = daily limit blown.
"""

import asyncio
from datetime import datetime, timezone

import aiohttp

from utils.http_client import HttpClient
from utils.logger import setup_logger


logger = setup_logger("news")

# High-impact keywords that PAUSE trading
HIGH_IMPACT = [
    # Macro
    "fed", "federal reserve", "fomc", "jerome powell", "interest rate",
    "rate hike", "rate cut", "cpi", "inflation", "ppi", "gdp",
    "treasury", "yield", "recession", "employment", "nonfarm",
    # Crypto specific
    "sec", "regulation", "ban", "crackdown", "hack", "exploit",
    "bankruptcy", "insolvency", "exchange down", "binance", "coinbase",
    "etf approval", "etf rejection", "whale dump", "flash crash",
    "liquidation cascade", "depegged", "rug pull", "sanctions",
    # Market structure
    "circuit breaker", "trading halt", "market crash", "black swan",
]

BULLISH_WORDS = [
    "etf approval", "institutional", "accumulation", "adoption",
    "partnership", "upgrade", "bullish", "rally", "breakout",
    "all-time high", "ath", "record high", "inflow",
]

BEARISH_WORDS = [
    "ban", "hack", "exploit", "crash", "dump", "liquidation",
    "bankruptcy", "fraud", "selloff", "outflow", "warning",
    "bearish", "decline", "collapse", "investigation",
]

# Sessions (IST = UTC+5:30)
# High-risk news windows in IST:
# FOMC:    Usually 11:30 PM IST (5:30 PM EST)
# CPI:     8:30 PM IST (3:00 PM EST)
# NFP:     6:00 PM IST (12:30 PM EST Fridays)

# Low-volume / avoid windows in IST:
AVOID_HOURS_IST = [0, 1, 2, 3, 4]   # 12AM–4AM IST = dead zone


class NewsFilter:

    def __init__(self, http_client: HttpClient):
        self._http = http_client
        self._last_check = None
        self._cached = None
        self.CACHE_MINS = 15  # Check news every 15 min


    async def _fetch_crypto_news(self, limit=30) -> list:
        """Fetch latest crypto news from CryptoCompare (free, no key)."""
        try:
            resp_json = await self._http.request_json(
                "https://min-api.cryptocompare.com/data/v2/news/",
                params={"lang": "EN", "sortOrder": "latest", "limit": limit},
                method="GET",
                timeout=aiohttp.ClientTimeout(total=10),
                expected_status=(200,),
                log_ctx="news/cryptocompare",
            )
            if not resp_json:
                return []
            return resp_json.get("Data", [])

        except Exception as e:
            logger.warning(f"News fetch error: {e}")
            return []

    def _analyze_articles(self, articles: list) -> dict:
        """Score news sentiment and detect high-impact events."""
        now_ts        = datetime.now(timezone.utc).timestamp()
        bull          = 0
        bear          = 0
        high_impact   = False
        impact_alerts = []
        recent_count  = 0

        for art in articles:
            pub_ts    = art.get("published_on", 0)
            age_hours = (now_ts - pub_ts) / 3600

            if age_hours > 4:   # Only look at last 4 hours
                continue

            recent_count += 1
            text = (
                art.get("title", "") + " " +
                art.get("body", "")[:300]
            ).lower()

            # High-impact check
            for kw in HIGH_IMPACT:
                if kw in text:
                    high_impact = True
                    alert = art.get("title", "")[:70]
                    if alert not in impact_alerts:
                        impact_alerts.append(f"📰 {alert}...")
                    break

            for kw in BULLISH_WORDS:
                if kw in text:
                    bull += 1
            for kw in BEARISH_WORDS:
                if kw in text:
                    bear += 1

        total = bull + bear
        if total > 0:
            bull_pct = bull / total * 100
            bear_pct = bear / total * 100
        else:
            bull_pct = bear_pct = 50.0

        if bear > bull * 2:       overall = "VERY_BEARISH"
        elif bear > bull:         overall = "BEARISH"
        elif bull > bear * 2:     overall = "VERY_BULLISH"
        elif bull > bear:         overall = "BULLISH"
        else:                     overall = "NEUTRAL"

        return {
            "overall":       overall,
            "bull_score":    bull,
            "bear_score":    bear,
            "bull_pct":      round(bull_pct, 1),
            "bear_pct":      round(bear_pct, 1),
            "high_impact":   high_impact,
            "should_pause":  high_impact,
            "alerts":        impact_alerts[:3],
            "recent_count":  recent_count,
            "checked_at":    datetime.now().strftime("%H:%M:%S"),
        }

    def _check_session_time(self) -> dict:
        """
        Session quality check (IST times):
        BEST  → London (1:30 PM – 5:30 PM IST) + NY overlap (6:30 PM – 10:30 PM IST)
        OK    → NY solo (10:30 PM – 12 AM IST)
        AVOID → Asian dead zone (12 AM – 7 AM IST)
        """
        hour = datetime.now().hour   # Local hour (IST)

        if hour in AVOID_HOURS_IST:
            return {
                "session":     "DEAD_ZONE",
                "quality":     "POOR",
                "should_skip": True,
                "note":        f"⚠️ Dead zone ({hour}:00 IST) — low volume, unreliable signals",
            }
        elif 13 <= hour <= 17:
            return {
                "session":     "LONDON",
                "quality":     "BEST",
                "should_skip": False,
                "note":        "✅ London session — high volume, strong signals",
            }
        elif 18 <= hour <= 22:
            return {
                "session":     "NEW_YORK",
                "quality":     "BEST",
                "should_skip": False,
                "note":        "✅ NY session — best liquidity, strong signals",
            }
        elif 7 <= hour <= 12:
            return {
                "session":     "ASIAN",
                "quality":     "OK",
                "should_skip": False,
                "note":        "🟡 Asian session — moderate volume",
            }
        else:
            return {
                "session":     "TRANSITION",
                "quality":     "OK",
                "should_skip": False,
                "note":        "🟡 Session transition",
            }

    async def check(self) -> dict:
        """
        Full check — news + session quality.
        Cached for 15 minutes.
        Returns combined result.
        """
        now = datetime.now()

        # Use cache if fresh
        if self._last_check and self._cached:
            age_mins = (now - self._last_check).seconds / 60
            if age_mins < self.CACHE_MINS:
                # Always recalc session (time-sensitive)
                self._cached["session"] = self._check_session_time()
                return self._cached

        # Fetch fresh news
        articles = await self._fetch_crypto_news()
        news     = self._analyze_articles(articles)
        session  = self._check_session_time()

        result = {
            "news":        news,
            "session":     session,
            "should_pause": news["should_pause"] or session["should_skip"],
            "pause_reason": (
                "High-impact news detected" if news["should_pause"]
                else ("Dead zone — low volume" if session["should_skip"]
                else None)
            ),
        }

        self._last_check = now
        self._cached     = result

        # Log
        if news["should_pause"]:
            logger.warning(f"🚨 News pause triggered! Alerts: {news['alerts']}")
        logger.info(
            f"  📰 News: {news['overall']} | Session: {session['session']} ({session['quality']})"
        )

        return result

    async def close(self):
        # Shared HttpClient is owned by main().
        return

