import asyncio
import logging
import sys
from config import Config
from client import PolymarketClient
from telegram_notifier import TelegramNotifier

# Setup premium logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PolymarketBot.Core")

class VolumeBot:
    def __init__(self):
        Config.validate()
        self.client = PolymarketClient()
        self.notifier = TelegramNotifier()
        self.strategy = Config.STRATEGY
        self.order_size = Config.ORDER_SIZE
        self.spread = Config.SPREAD
        self.max_position = Config.MAX_POSITION
        self.poll_interval = Config.POLL_INTERVAL
        self.is_running = False
        # Track last error per market to avoid Telegram spam
        self._last_errors = {}  # market_slug -> (error_hash, timestamp)
        self._error_cooldown_seconds = 300  # 5 minutes

    def _should_notify_error(self, market_slug, error_msg):
        """Returns True if we should send this error to Telegram (new error or cooldown passed)."""
        import hashlib, time
        error_hash = hashlib.md5(error_msg.encode()).hexdigest()
        now = time.time()
        last_hash, last_time = self._last_errors.get(market_slug, (None, 0))
        if last_hash == error_hash and (now - last_time) < self._error_cooldown_seconds:
            return False
        self._last_errors[market_slug] = (error_hash, now)
        return True

    def _format_error_for_telegram(self, market_question, error_msg):
        """Formats an error message nicely for Telegram (truncates, escapes markdown)."""
        # Truncate question
        q = market_question[:55] + "..." if len(market_question) > 55 else market_question
        # Clean error message: remove backticks, newlines, truncate
        clean = error_msg.replace("`", "'").replace("\n", " | ")
        if len(clean) > 200:
            clean = clean[:197] + "..."
        return f"⚠️ **Market Error**\nMarket: `{q}`\n`{clean}`"

    async def start(self):
        """Starts the main bot execution loop."""
        logger.info("==================================================")
        logger.info("      POLYMARKET WORLD CUP VOLUME FARMING BOT     ")
        logger.info("==================================================")
        logger.info(f"Strategy:       {self.strategy.upper()}")
        logger.info(f"Order Size:     {self.order_size} USDC")
        logger.info(f"Spread:         {self.spread}")
        logger.info(f"Max Position:   {self.max_position} shares")
        logger.info(f"Poll Interval:  {self.poll_interval}s")
        logger.info(f"Dry Run Mode:   {Config.DRY_RUN}")
        logger.info("==================================================")
        
        # Send startup alert to Telegram
        await self.notifier.send_message(
            f"🤖 **Polymarket Volume Bot Started**\n"
            f"• Strategy: `{self.strategy.upper()}`\n"
            f"• Order Size: `{self.order_size} USDC`\n"
            f"• Spread: `{self.spread}`\n"
            f"• Dry Run: `{Config.DRY_RUN}`"
        )
        
        self.is_running = True
        try:
            while self.is_running:
                logger.info("Starting polling cycle...")
                # 1. Fetch active World Cup markets
                markets = self.client.fetch_world_cup_markets()
                
                if not markets:
                    logger.warning("No active World Cup markets found. Sleeping...")
                    await asyncio.sleep(self.poll_interval)
                    continue

                for market in markets:
                    try:
                        logger.info(f"Analyzing market: {market['question']}")
                        if self.strategy == "market_making":
                            await self._run_market_making(market)
                        elif self.strategy == "yes_no_offset":
                            await self._run_yes_no_offset(market)
                    except Exception as e:
                        market_slug = market.get('slug', 'unknown')
                        error_msg = f"Error processing market {market_slug}: {e}"
                        logger.error(error_msg)
                        if self._should_notify_error(market_slug, error_msg):
                            tg_msg = self._format_error_for_telegram(market.get('question', 'Unknown'), str(e))
                            await self.notifier.send_message(tg_msg)
                        else:
                            logger.info(f"Suppressing duplicate Telegram alert for {market_slug} (cooldown active).")
                
                logger.info(f"Cycle complete. Sleeping for {self.poll_interval}s...\n")
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            logger.info("Bot execution cancelled.")
        except Exception as e:
            logger.error(f"Fatal exception in core loop: {e}")
            await self.notifier.send_message(f"🚨 **Fatal Bot Error in Main Loop**\n`{str(e)}`")
        finally:
            await self.shutdown()

    async def _run_market_making(self, market):
        """
        Executes Dual-Buy Market Making strategy on a market:
        - Fetch midpoint price M for YES token.
        - Calculate bid for YES = M - spread/2
        - Calculate bid for NO = (1 - M) - spread/2
        - Cancel previous orders on this market.
        - Place new limit orders.
        """
        yes_token = market["yes_token"]
        no_token = market["no_token"]

        # 1. Fetch current midpoint price
        try:
            mid_yes = self.client.get_midpoint_price(yes_token)
        except Exception:
            # Fallback to Gamma API prices if CLOB midpoint fails
            mid_yes = float(market["prices"][0])

        mid_no = 1.0 - mid_yes
        logger.info(f"Prices - YES Midpoint: {mid_yes:.2f} | NO Midpoint: {mid_no:.2f}")

        # 2. Check current positions to manage inventory risk
        pos_yes = self.client.get_position(yes_token)
        pos_no = self.client.get_position(no_token)
        logger.info(f"Positions - YES: {pos_yes} shares | NO: {pos_no} shares")

        # 3. Calculate order prices and sizes
        bid_price_yes = round(mid_yes - (self.spread / 2.0), 2)
        bid_price_no = round(mid_no - (self.spread / 2.0), 2)

        # Boundaries check
        bid_price_yes = max(0.01, min(0.99, bid_price_yes))
        bid_price_no = max(0.01, min(0.99, bid_price_no))

        # Size in shares = USDC Order size / Price
        size_yes = round(self.order_size / bid_price_yes, 2)
        size_no = round(self.order_size / bid_price_no, 2)

        # 4. Cancel existing open orders before placing new ones
        self.client.cancel_all_orders()

        # 5. Place Limit Bids (subject to Max Position thresholds)
        orders_summary = []
        if pos_yes < self.max_position:
            logger.info(f"Placing Bid for YES: {size_yes} shares @ {bid_price_yes:.2f}")
            self.client.place_limit_order(yes_token, bid_price_yes, size_yes, "buy")
            orders_summary.append(f"• BUY YES: `{size_yes} shares @ {bid_price_yes}`")
        else:
            logger.warning(f"YES position ({pos_yes}) exceeds max ({self.max_position}). Skipping YES bid.")

        if pos_no < self.max_position:
            logger.info(f"Placing Bid for NO: {size_no} shares @ {bid_price_no:.2f}")
            self.client.place_limit_order(no_token, bid_price_no, size_no, "buy")
            orders_summary.append(f"• BUY NO: `{size_no} shares @ {bid_price_no}`")
        else:
            logger.warning(f"NO position ({pos_no}) exceeds max ({self.max_position}). Skipping NO bid.")

        # 6. If we have inventory (both YES and NO), we can place limit asks to close them out
        if pos_yes > 5.0:  # Minimum share size for sell
            ask_price_yes = round(mid_yes + (self.spread / 2.0), 2)
            ask_price_yes = max(0.01, min(0.99, ask_price_yes))
            logger.info(f"Placing Ask for YES: {pos_yes} shares @ {ask_price_yes:.2f}")
            self.client.place_limit_order(yes_token, ask_price_yes, pos_yes, "sell")
            orders_summary.append(f"• SELL YES: `{pos_yes} shares @ {ask_price_yes}`")

        if pos_no > 5.0:
            ask_price_no = round(mid_no + (self.spread / 2.0), 2)
            ask_price_no = max(0.01, min(0.99, ask_price_no))
            logger.info(f"Placing Ask for NO: {pos_no} shares @ {ask_price_no:.2f}")
            self.client.place_limit_order(no_token, ask_price_no, pos_no, "sell")
            orders_summary.append(f"• SELL NO: `{pos_no} shares @ {ask_price_no}`")
            
        if orders_summary:
            summary_text = "\n".join(orders_summary)
            await self.notifier.send_message(
                f"📊 **Market Making Orders Placed**\n"
                f"Market: `{market['question'][:60]}...`\n"
                f"{summary_text}"
            )

    async def _run_yes_no_offset(self, market):
        """
        Executes Yes/No Offset strategy on a market:
        - Place buy order for YES.
        - Place buy order for NO.
        - Results in instant volume with neutral risk.
        """
        yes_token = market["yes_token"]
        no_token = market["no_token"]

        try:
            mid_yes = self.client.get_midpoint_price(yes_token)
        except Exception:
            mid_yes = float(market["prices"][0])
        mid_no = 1.0 - mid_yes

        # Use midpoint as the order price (acts as immediate taker or tight maker limit)
        price_yes = round(mid_yes, 2)
        price_no = round(mid_no, 2)

        size_yes = round(self.order_size / price_yes, 2)
        size_no = round(self.order_size / price_no, 2)

        logger.info(f"Offsetting: Buying {size_yes} YES shares @ {price_yes:.2f} AND {size_no} NO shares @ {price_no:.2f}")
        
        # Place both orders
        self.client.place_limit_order(yes_token, price_yes, size_yes, "buy")
        self.client.place_limit_order(no_token, price_no, size_no, "buy")
        
        await self.notifier.send_message(
            f"⚡ **Offset Orders Executed**\n"
            f"Market: `{market['question'][:60]}...`\n"
            f"• BUY YES: `{size_yes} shares @ {price_yes}`\n"
            f"• BUY NO: `{size_no} shares @ {price_no}`"
        )

    async def shutdown(self):
        """Cancels orders and stops the bot."""
        logger.info("Shutting down bot. Cancelling all open orders...")
        try:
            self.client.cancel_all_orders()
        except Exception as e:
            logger.error(f"Error canceling orders during shutdown: {e}")
        await self.notifier.send_message("🛑 **Polymarket Volume Bot Stopped**")
        logger.info("Shutdown complete.")

def main():
    bot = VolumeBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

if __name__ == "__main__":
    main()
