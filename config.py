import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Wallet private key
    PK = os.getenv("PK")
    
    # RPC URL for Polygon network (defaults to public RPC)
    RPC_URL = os.getenv("RPC_URL", "https://polygon-rpc.com")
    
    # Strategy to use: "market_making" or "yes_no_offset"
    STRATEGY = os.getenv("STRATEGY", "market_making").lower()
    
    # Order size in USDC (Polymarket CLOB has minimum order sizes, typically $1 / 5 shares)
    ORDER_SIZE = float(os.getenv("ORDER_SIZE", "5.0"))
    
    # Bid-ask spread for market making (e.g. 0.01 represents 1 cent spread from midpoint)
    SPREAD = float(os.getenv("SPREAD", "0.01"))
    
    # Maximum position size in shares to hold before pausing buy orders
    MAX_POSITION = float(os.getenv("MAX_POSITION", "50.0"))
    
    # How often to check prices and update orders (seconds)
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
    
    # Simulation / Dry Run mode (enabled by default for safety)
    DRY_RUN = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")
    
    # API endpoints
    CLOB_API_URL = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
    GAMMA_API_URL = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")
    
    # Optional API credentials (will be derived from PK if not provided)
    API_KEY = os.getenv("API_KEY")
    API_SECRET = os.getenv("API_SECRET")
    API_PASSPHRASE = os.getenv("API_PASSPHRASE")

    # Optional signature type and funder (deposit wallet flow)
    # SIGNATURE_TYPE=3 (POLY_1271) is REQUIRED for deposit wallet flow on Polymarket.
    # If your account requires deposit wallet, set SIGNATURE_TYPE=3 and FUNDER=<your deposit address>.
    SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "3"))
    FUNDER = os.getenv("FUNDER")

    # Telegram Notification configurations
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    @classmethod
    def validate(cls):
        """Validates configuration settings."""
        if not cls.DRY_RUN and not cls.PK:
            raise ValueError("PRIVATE KEY (PK) must be set in .env to run in production mode.")
        if not cls.DRY_RUN and not cls.FUNDER:
            raise ValueError(
                "FUNDER (deposit wallet address) must be set in .env to run in production mode.\n"
                "Polymarket requires deposit wallet flow for most accounts.\n"
                "Get your deposit address from your Polymarket profile and set:\n"
                "  FUNDER=0xYourDepositWalletAddress\n"
                "  SIGNATURE_TYPE=3"
            )
        if cls.SIGNATURE_TYPE not in (1, 3):
            raise ValueError(f"SIGNATURE_TYPE must be 1 or 3. Got {cls.SIGNATURE_TYPE}.")
        if cls.STRATEGY not in ("market_making", "yes_no_offset"):
            raise ValueError(f"Invalid strategy: {cls.STRATEGY}. Must be 'market_making' or 'yes_no_offset'.")
        if cls.ORDER_SIZE <= 0:
            raise ValueError("ORDER_SIZE must be greater than 0.")
        if cls.SPREAD <= 0:
            raise ValueError("SPREAD must be greater than 0.")
        if cls.MAX_POSITION <= 0:
            raise ValueError("MAX_POSITION must be greater than 0.")
        if cls.POLL_INTERVAL < 1:
            raise ValueError("POLL_INTERVAL must be at least 1 second.")
        if (cls.TELEGRAM_BOT_TOKEN and not cls.TELEGRAM_CHAT_ID) or (not cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID):
            raise ValueError("Both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set to enable Telegram alerts.")

