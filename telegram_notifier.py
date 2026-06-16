import asyncio
import logging
import requests
from config import Config

logger = logging.getLogger("PolymarketBot.Telegram")

class TelegramNotifier:
    def __init__(self):
        self.enabled = (
            Config.API_KEY is not None # Config load check helper
            and os_env_has_telegram()
        )
        # Note: we will load values dynamically from Config
        self.bot_token = getattr(Config, "TELEGRAM_BOT_TOKEN", None)
        self.chat_id = getattr(Config, "TELEGRAM_CHAT_ID", None)
        
        self.enabled = bool(self.bot_token and self.chat_id)
        if self.enabled:
            logger.info("Telegram notification integration enabled.")
        else:
            logger.info("Telegram notification integration disabled (token or chat ID not set).")

    def send_message_sync(self, text):
        """Synchronous implementation of sending message (runs in background thread)."""
        if not self.enabled:
            return False
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            # Short timeout to avoid hanging the thread
            response = requests.post(url, json=payload, timeout=8)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_message(self, text):
        """Asynchronously sends a Telegram notification."""
        if not self.enabled:
            return
            
        logger.info(f"Sending Telegram alert: {text[:60]}...")
        # Run blocking requests call in a separate thread pool using asyncio.to_thread
        await asyncio.to_thread(self.send_message_sync, text)

def os_env_has_telegram():
    import os
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
