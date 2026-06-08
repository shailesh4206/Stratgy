import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import Config
from utils.http_client import HttpClient
from signals.telegram_bot import TelegramBot

async def main():
    config = Config()
    http = HttpClient()
    tg = TelegramBot(config, http)
    
    dummy_signal = {
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "price": 69550.00,
        "timestamp": datetime.now(),
        "confidence": 85,
        "quality": "HIGH",
        "adx": 35.5,
        "adx_strength": "STRONG",
        "obv_signal": "UPTREND",
        "fib_level": "0.618 Golden Ratio",
        "candle": "Bullish Engulfing",
        "regime": "Trending",
        "session": "LONDON",
        "rsi": 45,
        "rel_volume": 2.5,
        "funding_rate": 0.015,
        "funding_bias": "BULLISH",
        "reasons": [
            "Price bounced exactly from 0.618 Fibonacci level.",
            "Strong bullish engulfing candle on 15m timeframe.",
            "Volume is 2.5x higher than average.",
            "ADX confirms a strong trend is forming.",
            "This is a test signal for checking formatting."
        ],
        "levels": {
            "entry_low": 69400.00,
            "entry_high": 69500.00,
            "stop_loss": 68900.00,
            "target_1": 70000.00,
            "target_2": 70500.00,
            "target_3": 71500.00,
            "risk_reward": 3.5
        },
        "tr": {
            "stage": "Bot Live",
            "daily_pct": 2.5,
            "total_pct": 12.0,
            "trades_today": 1,
            "profit_pct": 12,
            "profit_made": "$600",
            "target": "$5000",
            "daily_loss": 0,
            "daily_limit": 100,
            "daily_remaining": "$100",
            "total_loss": 0,
            "total_limit": 200,
            "trading_days": 15,
            "profit_est": 45.0,
            "warnings": []
        }
    }
    
    success = await tg.send_signal(dummy_signal)
    if success:
        print("Fake signal sent successfully!")
    else:
        print("Failed to send fake signal.")
        
    await http.close()

if __name__ == "__main__":
    asyncio.run(main())
