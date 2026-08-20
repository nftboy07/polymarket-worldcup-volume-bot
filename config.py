import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return value


class Config:
    PK = os.getenv("PK")
    RPC_URL = os.getenv("RPC_URL", "https://polygon-rpc.com")

    # Only genuine passive market making is enabled. The old offset mode has been removed.
    STRATEGY = os.getenv("STRATEGY", "market_making").strip().lower()

    ORDER_SIZE = _float("ORDER_SIZE", 5.0)
    SPREAD = _float("SPREAD", 0.02)
    MAX_POSITION = _float("MAX_POSITION", 50.0)
    MAX_TOTAL_EXPOSURE = _float("MAX_TOTAL_EXPOSURE", 100.0)
    MAX_OPEN_ORDERS = int(os.getenv("MAX_OPEN_ORDERS", "20"))
    MAX_MARKETS = int(os.getenv("MAX_MARKETS", "10"))
    MIN_LIQUIDITY = _float("MIN_LIQUIDITY", 10.0)
    MAX_SPREAD = _float("MAX_SPREAD", 0.20)
    STALE_ORDER_SECONDS = int(os.getenv("STALE_ORDER_SECONDS", "30"))
    REPRICE_THRESHOLD = _float("REPRICE_THRESHOLD", 0.01)
    MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "5"))
    POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2.0"))
    DRY_RUN = _bool("DRY_RUN", True)

    CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
    GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")
    API_PASSPHRASE = os.getenv("API_PASSPHRASE")
    SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "3"))
    FUNDER = os.getenv("FUNDER")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    @classmethod
    def validate(cls):
        if not cls.DRY_RUN and not cls.PK:
            raise ValueError("PK must be set when DRY_RUN=false")
        if not cls.DRY_RUN and not cls.FUNDER:
            raise ValueError("FUNDER must be set when DRY_RUN=false")
        if cls.SIGNATURE_TYPE not in (1, 3):
            raise ValueError("SIGNATURE_TYPE must be 1 or 3")
        if cls.STRATEGY != "market_making":
            raise ValueError("Only STRATEGY=market_making is supported")
        if cls.ORDER_SIZE <= 0 or cls.SPREAD <= 0:
            raise ValueError("ORDER_SIZE and SPREAD must be > 0")
        if cls.MAX_POSITION <= 0 or cls.MAX_TOTAL_EXPOSURE <= 0:
            raise ValueError("Position and exposure limits must be > 0")
        if cls.MAX_OPEN_ORDERS < 1 or cls.MAX_MARKETS < 1:
            raise ValueError("MAX_OPEN_ORDERS and MAX_MARKETS must be >= 1")
        if cls.STALE_ORDER_SECONDS < 1 or cls.POLL_INTERVAL <= 0:
            raise ValueError("STALE_ORDER_SECONDS and POLL_INTERVAL must be > 0")
        if cls.REPRICE_THRESHOLD < 0 or cls.MAX_SPREAD <= 0:
            raise ValueError("Invalid spread thresholds")
        if cls.MAX_CONSECUTIVE_ERRORS < 1:
            raise ValueError("MAX_CONSECUTIVE_ERRORS must be >= 1")
        if bool(cls.TELEGRAM_BOT_TOKEN) != bool(cls.TELEGRAM_CHAT_ID):
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be supplied together")
