# analysis/smc_analyzer.py
"""
Smart Money Concepts (SMC) Analyzer
- Order Blocks
- Fair Value Gaps (FVG)
- Liquidity Pools
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Market Structure (HH/HL/LH/LL)
"""

import pandas as pd
import numpy as np
from utils.logger import setup_logger

logger = setup_logger("smc")


class SMCAnalyzer:

    @staticmethod
    def detect_market_structure(df: pd.DataFrame, lookback: int = 10) -> dict:
        """Detect HH, HL, LH, LL and trend direction."""
        highs = df["high"].values
        lows  = df["low"].values

        # Find swing highs and lows
        swing_highs = []
        swing_lows  = []

        for i in range(lookback, len(highs) - lookback):
            if highs[i] == max(highs[i - lookback:i + lookback + 1]):
                swing_highs.append((i, highs[i]))
            if lows[i] == min(lows[i - lookback:i + lookback + 1]):
                swing_lows.append((i, lows[i]))

        trend = "NEUTRAL"
        hh = hl = lh = ll = False

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            last_sh  = swing_highs[-1][1]
            prev_sh  = swing_highs[-2][1]
            last_sl  = swing_lows[-1][1]
            prev_sl  = swing_lows[-2][1]

            hh = last_sh > prev_sh
            hl = last_sl > prev_sl
            lh = last_sh < prev_sh
            ll = last_sl < prev_sl

            if hh and hl:
                trend = "BULLISH"
            elif lh and ll:
                trend = "BEARISH"
            else:
                trend = "NEUTRAL"

        return {
            "trend":       trend,
            "HH":          hh,
            "HL":          hl,
            "LH":          lh,
            "LL":          ll,
            "swing_highs": swing_highs[-3:] if swing_highs else [],
            "swing_lows":  swing_lows[-3:]  if swing_lows  else [],
        }

    @staticmethod
    def detect_order_blocks(df: pd.DataFrame, n: int = 20) -> dict:
        """
        Detect Bullish and Bearish Order Blocks.
        Bullish OB: Last bearish candle before a strong bullish move.
        Bearish OB: Last bullish candle before a strong bearish move.
        """
        bullish_obs = []
        bearish_obs = []

        closes = df["close"].values
        opens  = df["open"].values
        highs  = df["high"].values
        lows   = df["low"].values

        for i in range(2, len(df) - n):
            # Bearish OB: bullish candle followed by strong bearish move
            if closes[i] > opens[i]:  # bullish candle
                future_move = min(lows[i+1:i+n]) - lows[i]
                candle_size = highs[i] - lows[i]
                if future_move < -candle_size * 2:
                    bearish_obs.append({
                        "idx":  i,
                        "top":  highs[i],
                        "bot":  opens[i],
                        "mid":  (highs[i] + opens[i]) / 2,
                        "type": "BEARISH_OB",
                    })

            # Bullish OB: bearish candle followed by strong bullish move
            if closes[i] < opens[i]:  # bearish candle
                future_move = max(highs[i+1:i+n]) - highs[i]
                candle_size = highs[i] - lows[i]
                if future_move > candle_size * 2:
                    bullish_obs.append({
                        "idx":  i,
                        "top":  opens[i],
                        "bot":  lows[i],
                        "mid":  (opens[i] + lows[i]) / 2,
                        "type": "BULLISH_OB",
                    })

        return {
            "bullish_obs": bullish_obs[-3:],
            "bearish_obs": bearish_obs[-3:],
        }

    @staticmethod
    def detect_fvg(df: pd.DataFrame, n: int = 50) -> dict:
        """
        Detect Fair Value Gaps (FVG / Imbalance zones).
        Bullish FVG: candle[i].low > candle[i-2].high
        Bearish FVG: candle[i].high < candle[i-2].low
        """
        bullish_fvgs = []
        bearish_fvgs = []

        highs  = df["high"].values
        lows   = df["low"].values

        start = max(2, len(df) - n)
        for i in range(start, len(df)):
            # Bullish FVG
            if lows[i] > highs[i - 2]:
                bullish_fvgs.append({
                    "top":  lows[i],
                    "bot":  highs[i - 2],
                    "mid":  (lows[i] + highs[i - 2]) / 2,
                    "type": "BULLISH_FVG",
                })
            # Bearish FVG
            if highs[i] < lows[i - 2]:
                bearish_fvgs.append({
                    "top":  lows[i - 2],
                    "bot":  highs[i],
                    "mid":  (lows[i - 2] + highs[i]) / 2,
                    "type": "BEARISH_FVG",
                })

        return {
            "bullish_fvgs": bullish_fvgs[-3:],
            "bearish_fvgs": bearish_fvgs[-3:],
        }

    @staticmethod
    def detect_liquidity(df: pd.DataFrame) -> dict:
        """
        Detect liquidity pools:
        - Equal Highs (resistance liquidity)
        - Equal Lows (support liquidity)
        """
        highs  = df["high"].values[-50:]
        lows   = df["low"].values[-50:]
        closes = df["close"].values[-50:]
        tol    = 0.003  # 0.3% tolerance for "equal"

        # Equal highs clusters
        equal_highs = []
        for i in range(len(highs) - 1):
            for j in range(i + 1, len(highs)):
                if abs(highs[i] - highs[j]) / highs[i] < tol:
                    equal_highs.append(highs[i])

        equal_lows = []
        for i in range(len(lows) - 1):
            for j in range(i + 1, len(lows)):
                if abs(lows[i] - lows[j]) / lows[i] < tol:
                    equal_lows.append(lows[i])

        current_price = closes[-1]

        # Nearest liquidity above and below
        above = [h for h in equal_highs if h > current_price]
        below = [l for l in equal_lows  if l < current_price]

        return {
            "equal_highs":      sorted(set([round(h, 1) for h in equal_highs]))[-3:],
            "equal_lows":       sorted(set([round(l, 1) for l in equal_lows]))[:3],
            "nearest_liq_above": min(above) if above else None,
            "nearest_liq_below": max(below) if below else None,
        }

    @staticmethod
    def detect_bos_choch(df: pd.DataFrame) -> dict:
        """Detect Break of Structure and Change of Character."""
        ms = SMCAnalyzer.detect_market_structure(df)

        swing_highs = ms["swing_highs"]
        swing_lows  = ms["swing_lows"]

        bos_bullish  = False
        bos_bearish  = False
        choch        = False

        current_price = float(df["close"].iloc[-1])

        if swing_highs and len(swing_highs) >= 2:
            last_sh = swing_highs[-1][1]
            prev_sh = swing_highs[-2][1]
            # BOS Bullish: price breaks above last swing high
            if current_price > last_sh and ms["trend"] == "BEARISH":
                choch = True  # Trend change signal
            elif current_price > last_sh:
                bos_bullish = True

        if swing_lows and len(swing_lows) >= 2:
            last_sl = swing_lows[-1][1]
            # BOS Bearish: price breaks below last swing low
            if current_price < last_sl:
                bos_bearish = True

        return {
            "BOS_bullish": bos_bullish,
            "BOS_bearish": bos_bearish,
            "CHoCH":       choch,
        }
