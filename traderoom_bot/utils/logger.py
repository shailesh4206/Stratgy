# utils/logger.py
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any


_EMOJI_RE = re.compile(
    "[" 
    "\U0001F300-\U0001FAFF"  # emoji blocks
    "\U00002600-\U000027BF"  # misc symbols
    "]+",
    flags=re.UNICODE,
)


def sanitize_text(text: Any, *, replace_emojis: bool = False) -> str:
    """Convert to str and make it safe for console/file logging."""
    if text is None:
        return ""
    s = str(text)
    if replace_emojis:
        s = _EMOJI_RE.sub("[EMOJI]", s)
    # Keep logs one-line to avoid log-splitting.
    s = s.replace("\r", " ").replace("\n", "↩")
    return s


class _SanitizeFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: str | None = None, *, replace_emojis: bool = False):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._replace_emojis = replace_emojis

    def format(self, record: logging.LogRecord) -> str:
        # Ensure msg is sanitized.
        record.msg = sanitize_text(record.msg, replace_emojis=self._replace_emojis)
        return super().format(record)


def _windows_force_utf8_console() -> None:
    # Helps avoid mojibake on Windows when console code page isn't UTF-8.
    try:
        if os.name == "nt":
            # Python 3.7+ respects UTF-8 mode; prefer that when available.
            if "PYTHONUTF8" not in os.environ:
                os.environ["PYTHONUTF8"] = "1"
            # Best-effort: set stdout encoding.
            if getattr(sys.stdout, "encoding", None) not in ("utf-8", "UTF-8"):
                try:
                    sys.stdout.reconfigure(encoding="utf-8")
                except Exception:
                    pass
    except Exception:
        pass


def setup_logger(name: str) -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    # Ensure UTF-8 everywhere (Windows console + file) to avoid UnicodeEncodeError.
    _windows_force_utf8_console()


    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # Default: keep emojis; Telegram uses its own escaping.
    replace_emojis = os.getenv("REPLACE_EMOJIS_IN_LOGS", "0").lower() in {"1", "true", "yes"}

    logger.setLevel(logging.INFO)

    fmt = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

    # Console handler
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_SanitizeFormatter(fmt, datefmt="%H:%M:%S", replace_emojis=replace_emojis))

    # File handler (UTF-8)
    log_file = f"logs/bot_{datetime.now().strftime('%Y%m%d')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_SanitizeFormatter(fmt, replace_emojis=replace_emojis))

    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.propagate = False
    return logger

