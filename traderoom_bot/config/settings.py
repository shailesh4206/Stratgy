# config/settings.py
"""
TRADEROOM $5,000 — FINAL BEST VERSION
Daily Limit : $100 (2%) — bot stops at $80
Max Loss    : $200 (4%) — bot stops at $160
Risk/Trade  : $15  (0.3%)
Min RR      : 1:3
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from utils.logger import setup_logger

_logger = setup_logger("settings")

# Load .env from multiple possible locations (production-evidence-based):
# 1) project_root/.env
# 2) traderoom_bot/.env
# 3) current_working_directory/.env
#
# The runtime log shows a .env at:
#   C:\Users\mitka\Downloads\stratgy\traderoom_bot\traderoom_bot.env
# We keep logic generic and search the allowed locations.

_ROOT_PATH = Path(__file__).resolve().parents[1]  # .../traderoom_bot
_PROJECT_ROOT = _ROOT_PATH.parent               # .../stratgy
_CWD = Path.cwd()

# REQUIRED explicit search paths:
# - project_root/.env
# - traderoom_bot/.env
# - traderoom_bot/traderoom_bot.env
# - current working directory .env
_candidate_paths = [
    _PROJECT_ROOT / ".env",
    _ROOT_PATH / ".env",
    _ROOT_PATH / "traderoom_bot.env",
    _CWD / ".env",
]

_ENV_PATH = None
for p in _candidate_paths:
    if p.exists() and p.is_file():
        _ENV_PATH = p
        break

# Load deterministically from the first existing allowed file.
# If none exist, allow env vars from OS without failing.
loaded_ok = False
if _ENV_PATH is not None:
    loaded_ok = load_dotenv(dotenv_path=str(_ENV_PATH), override=False)
    # debug logs required by task
    _logger.info(f"Loaded .env: {_ENV_PATH}")
else:
    load_dotenv(override=False)
    _logger.info("No allowed .env file found; using OS env vars only")

# Support both env var names: TELEGRAM_TOKEN / TELEGRAM_BOT_TOKEN
_env_token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
_env_chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
_logger.info(f"TELEGRAM_TOKEN_LOADED={bool(_env_token) and _env_token != 'YOUR_TOKEN_HERE'}")
_logger.info(f"TELEGRAM_CHAT_ID_LOADED={bool(_env_chat_id) and _env_chat_id != 'YOUR_CHAT_ID_HERE'}")




class Config:


    # ── TELEGRAM ─────────────────────────────────────────────
    # Support BOTH env var names:
    # - TELEGRAM_TOKEN
    # - TELEGRAM_BOT_TOKEN
    TELEGRAM_BOT_TOKEN = (
        os.getenv("TELEGRAM_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or ""
    ).strip()

    TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()


    MODE = "SIGNAL_ONLY"

    # Exposed for startup diagnostics/logging
    ENV_PATH = str(_ENV_PATH) if _ENV_PATH is not None else "NOT_FOUND"

    TELEGRAM_TOKEN_LOADED = bool(TELEGRAM_BOT_TOKEN) and TELEGRAM_BOT_TOKEN != "YOUR_TOKEN_HERE"
    TELEGRAM_CHAT_ID_LOADED = bool(TELEGRAM_CHAT_ID) and TELEGRAM_CHAT_ID != "YOUR_CHAT_ID_HERE"


    # ── TRADEROOM OFFICIAL RULES ($5K) ────────────────────────
    ACCOUNT_SIZE          = 5_000
    TR_DAILY_LOSS_LIMIT   = 250    # Official 5%
    TR_MAX_LOSS_LIMIT     = 500    # Official 10%

    # ── YOUR PERSONAL SAFE LIMITS (tighter = safer) ───────────
    # Bot stops HERE — well before TradeRoom limits
    MY_DAILY_LOSS_LIMIT   = 100    # 2%  — your choice
    MY_DAILY_STOP_AT      = 80     # Bot pauses at $80 (not $100) — extra buffer
    MY_MAX_LOSS_LIMIT     = 200    # 4%  — your choice
    MY_MAX_STOP_AT        = 160    # Bot pauses at $160 — extra buffer

    # ── RISK PER TRADE ────────────────────────────────────────
    RISK_PER_TRADE_USD    = 15     # $15 per trade — your choice
    RISK_PER_TRADE_PCT    = 0.3    # 0.3% of $5,000
    MAX_TRADES_PER_DAY    = 2      # Max 2 signals per day

    # ── SIGNAL QUALITY (strict) ───────────────────────────────
    MIN_CONFIDENCE        = 72     # Only 72%+ signals sent
    MIN_RISK_REWARD       = 3.0    # Minimum 1:3 RR
    MIN_VOLUME_RATIO      = 1.3    # Volume 1.3x above average
    SIGNAL_COOLDOWN_MINS  = 120    # 2 hour cooldown per pair

    # ── PAIRS ─────────────────────────────────────────────────
    PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # ── INDICATORS ───────────────────────────────────────────
    EMA_FAST=9; EMA_MED=21; EMA_SLOW=50; EMA_TREND=200
    RSI_PERIOD=14; RSI_OB=70; RSI_OS=30
    ATR_PERIOD=14; ATR_SL_MULT=1.5

    # ── SCAN ─────────────────────────────────────────────────
    SCAN_INTERVAL_SECONDS = 300

    # ── STAGE (update manually as you progress) ──────────────
    # "STAGE1" → "STAGE2" → "FUNDED"
    CURRENT_STAGE = "STAGE1"

    # Stage targets
    S1_PROFIT_TARGET  = 400   # 8% = $400
    S1_MIN_DAYS       = 5
    S2_PROFIT_TARGET  = 250   # 5% = $250
    S2_MIN_DAYS       = 5
    F_MIN_DAYS        = 7
