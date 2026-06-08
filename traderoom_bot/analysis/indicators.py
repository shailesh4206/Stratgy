# analysis/indicators.py
"""
Technical Indicators
EMA, RSI, MACD, ATR, VWAP, Bollinger Bands, Volume Analysis
"""

import pandas as pd
import numpy as np


class Indicators:

    @staticmethod
    def ema(df: pd.DataFrame, period: int, col: str = "close") -> pd.Series:
        return df[col].ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> dict:
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
        return vwap

    @staticmethod
    def bollinger_bands(df: pd.DataFrame, period=20, std_dev=2) -> dict:
        ma = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        return {
            "upper": ma + (std * std_dev),
            "middle": ma,
            "lower": ma - (std * std_dev),
        }

    @staticmethod
    def volume_analysis(df: pd.DataFrame, period: int = 20) -> dict:
        avg_vol = df["volume"].rolling(period).mean()
        rel_volume = df["volume"] / avg_vol
        vol_spike = rel_volume > 2.0

        # Delta volume (buying vs selling pressure per candle)
        delta = df["close"] - df["open"]
        buy_vol = df["volume"].where(delta > 0, df["volume"] * 0.5)
        sell_vol = df["volume"].where(delta < 0, df["volume"] * 0.5)

        return {
            "avg_volume": avg_vol,
            "relative_volume": rel_volume,
            "volume_spike": vol_spike,
            "buy_volume": buy_vol,
            "sell_volume": sell_vol,
            "current_rel_vol": float(rel_volume.iloc[-1]),
            "is_high_volume": float(rel_volume.iloc[-1]) > 1.2,
        }

    @staticmethod
    def compute_all(df: pd.DataFrame, config) -> dict:
        """Compute all indicators and return as dict of latest values."""
        ind = {}

        # EMAs
        ind["ema9"]   = Indicators.ema(df, config.EMA_FAST)
        ind["ema21"]  = Indicators.ema(df, config.EMA_MED)
        ind["ema50"]  = Indicators.ema(df, config.EMA_SLOW)
        ind["ema200"] = Indicators.ema(df, config.EMA_TREND)

        # RSI
        ind["rsi"] = Indicators.rsi(df, config.RSI_PERIOD)

        # MACD
        macd = Indicators.macd(df)
        ind["macd"]           = macd["macd"]
        ind["macd_signal"]    = macd["signal"]
        ind["macd_histogram"] = macd["histogram"]

        # ATR
        ind["atr"] = Indicators.atr(df, config.ATR_PERIOD)

        # VWAP
        ind["vwap"] = Indicators.vwap(df)

        # Volume
        vol = Indicators.volume_analysis(df)
        ind["volume_analysis"] = vol

        # Latest values (scalars)
        last = df.iloc[-1]
        ind["latest"] = {
            "close":       float(last["close"]),
            "high":        float(last["high"]),
            "low":         float(last["low"]),
            "volume":      float(last["volume"]),
            "ema9":        float(ind["ema9"].iloc[-1]),
            "ema21":       float(ind["ema21"].iloc[-1]),
            "ema50":       float(ind["ema50"].iloc[-1]),
            "ema200":      float(ind["ema200"].iloc[-1]),
            "rsi":         float(ind["rsi"].iloc[-1]),
            "macd":        float(ind["macd"].iloc[-1]),
            "macd_signal": float(ind["macd_signal"].iloc[-1]),
            "macd_hist":   float(ind["macd_histogram"].iloc[-1]),
            "atr":         float(ind["atr"].iloc[-1]),
            "vwap":        float(ind["vwap"].iloc[-1]),
            "rel_volume":  vol["current_rel_vol"],
            "high_volume": vol["is_high_volume"],
        }

        return ind
