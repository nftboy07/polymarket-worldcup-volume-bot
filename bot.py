import asyncio
import logging
import sys
import time
from config import Config
from client import PolymarketClient
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("PolymarketBot.Core")


class VolumeBot:
    def __init__(self):
        Config.validate()
        self.client = PolymarketClient()
        self.notifier = TelegramNotifier()
        self.is_running = False
        self.kill_switch = False
        self.consecutive_errors = 0
        self.market_error_counts = {}
        self.last_quotes = {}

    async def _call(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def _notify(self, message):
        try:
            await self.notifier.send_message(message)
        except Exception as exc:
            logger.warning("Telegram notification failed: %s", exc)

    @staticmethod
    def _order_field(order, *names, default=None):
        if isinstance(order, dict):
            for name in names:
                if name in order:
                    return order[name]
        else:
            for name in names:
                value = getattr(order, name, None)
                if value is not None:
                    return value
        return default

    def _normalize_open_order(self, order):
        return {
            "id": self._order_field(order, "id", "orderID", "order_id"),
            "token_id": self._order_field(order, "asset_id", "token_id", "tokenId"),
            "side": str(self._order_field(order, "side", default="")).upper(),
            "price": float(self._order_field(order, "price", default=0)),
            "size": float(self._order_field(order, "original_size", "size", default=0)),
            "created_at": self._order_field(order, "created_at", "createdAt", default=None),
        }

    async def _cancel_stale_orders(self, open_orders):
        now = time.time()
        for raw in open_orders:
            order = self._normalize_open_order(raw)
            if not order["id"]:
                continue
            created = order["created_at"]
            stale = False
            if isinstance(created, (int, float)):
                stale = now - float(created) > Config.STALE_ORDER_SECONDS
            if stale:
                try:
                    await self._call(self.client.cancel_order, order["id"])
                    logger.info("Canceled stale order %s", order["id"])
                except Exception as exc:
                    logger.warning("Could not cancel stale order %s: %s", order["id"], exc)

    async def _emergency_stop(self, reason):
        if self.kill_switch:
            return
        self.kill_switch = True
        self.is_running = False
        logger.error("EMERGENCY STOP: %s", reason)
        try:
            await self._call(self.client.cancel_all_orders)
        except Exception as exc:
            logger.critical("Emergency cancellation failed: %s", exc)
        await self._notify(f"🚨 **BOT HALTED**\nReason: `{reason[:250]}`")

    async def start(self):
        logger.info("Starting hardened Polymarket market maker")
        logger.info("Dry run=%s | order=$%.2f | spread=%.4f | max position=%.2f | max exposure=%.2f",
                    Config.DRY_RUN, Config.ORDER_SIZE, Config.SPREAD,
                    Config.MAX_POSITION, Config.MAX_TOTAL_EXPOSURE)
        await self._notify(
            f"🤖 **Polymarket MM Started**\n"
            f"• Dry run: `{Config.DRY_RUN}`\n"
            f"• Order size: `${Config.ORDER_SIZE:.2f}`\n"
            f"• Spread: `{Config.SPREAD:.4f}`\n"
            f"• Max exposure: `${Config.MAX_TOTAL_EXPOSURE:.2f}`"
        )
        self.is_running = True
        try:
            while self.is_running and not self.kill_switch:
                try:
                    await self._run_cycle()
                    self.consecutive_errors = 0
                except Exception as exc:
                    self.consecutive_errors += 1
                    logger.exception("Cycle failed (%s/%s)", self.consecutive_errors, Config.MAX_CONSECUTIVE_ERRORS)
                    if self.consecutive_errors >= Config.MAX_CONSECUTIVE_ERRORS:
                        await self._emergency_stop(f"{self.consecutive_errors} consecutive cycle failures: {exc}")
                        break
                await asyncio.sleep(Config.POLL_INTERVAL)
        finally:
            await self.shutdown()

    async def _run_cycle(self):
        markets = await self._call(self.client.fetch_world_cup_markets)
        if not markets:
            logger.info("No eligible active markets")
            return

        open_orders = await self._call(self.client.get_open_orders)
        if len(open_orders) > Config.MAX_OPEN_ORDERS:
            await self._emergency_stop("Open-order limit exceeded")
            return
        await self._cancel_stale_orders(open_orders)

        for market in markets[:Config.MAX_MARKETS]:
            if self.kill_switch:
                return
            try:
                await self._quote_market(market)
            except Exception as exc:
                slug = market.get("slug", "unknown")
                self.market_error_counts[slug] = self.market_error_counts.get(slug, 0) + 1
                logger.error("Market %s failed: %s", slug, exc)
                if self.market_error_counts[slug] >= Config.MAX_CONSECUTIVE_ERRORS:
                    await self._emergency_stop(f"Repeated failure on {slug}: {exc}")
                    return

    async def _quote_market(self, market):
        if not market.get("active", True):
            return
        if market.get("liquidity", 0) < Config.MIN_LIQUIDITY:
            logger.debug("Skipping %s: insufficient liquidity", market.get("slug"))
            return

        yes = market["yes_token"]
        no = market["no_token"]
        yes_bid, yes_ask, yes_mid = await self._call(self.client.quote_from_book, yes)
        no_bid, no_ask, no_mid = await self._call(self.client.quote_from_book, no)

        if yes_ask - yes_bid > Config.MAX_SPREAD or no_ask - no_bid > Config.MAX_SPREAD:
            logger.info("Skipping %s: book spread too wide", market.get("slug"))
            return

        pos_yes = await self._call(self.client.get_position, yes)
        pos_no = await self._call(self.client.get_position, no)
        current_exposure = abs(pos_yes) * yes_mid + abs(pos_no) * no_mid
        if current_exposure >= Config.MAX_TOTAL_EXPOSURE:
            logger.info("Skipping buys for %s: exposure %.2f >= %.2f", market.get("slug"), current_exposure, Config.MAX_TOTAL_EXPOSURE)
            return

        yes_rules = await self._call(self.client.get_market_rules, yes)
        no_rules = await self._call(self.client.get_market_rules, no)
        tick_yes = yes_rules["tick_size"]
        tick_no = no_rules["tick_size"]

        # Passive quotes only: improve neither side through the spread.
        yes_price = min(yes_ask - tick_yes, yes_mid - Config.SPREAD / 2)
        no_price = min(no_ask - tick_no, no_mid - Config.SPREAD / 2)
        yes_price = self.client.round_price(yes_price, tick_yes)
        no_price = self.client.round_price(no_price, tick_no)

        yes_size = Config.ORDER_SIZE / max(yes_price, 0.01)
        no_size = Config.ORDER_SIZE / max(no_price, 0.01)

        if pos_yes < Config.MAX_POSITION and current_exposure + Config.ORDER_SIZE <= Config.MAX_TOTAL_EXPOSURE:
            await self._ensure_quote(yes, "BUY", yes_price, yes_size, tick_yes)
        if pos_no < Config.MAX_POSITION and current_exposure + Config.ORDER_SIZE <= Config.MAX_TOTAL_EXPOSURE:
            await self._ensure_quote(no, "BUY", no_price, no_size, tick_no)

        # Inventory reduction: only quote an ask when inventory exists.
        if pos_yes > 0:
            ask = max(yes_bid + tick_yes, yes_mid + Config.SPREAD / 2)
            await self._ensure_quote(yes, "SELL", self.client.round_price(ask, tick_yes), pos_yes, tick_yes)
        if pos_no > 0:
            ask = max(no_bid + tick_no, no_mid + Config.SPREAD / 2)
            await self._ensure_quote(no, "SELL", self.client.round_price(ask, tick_no), pos_no, tick_no)

    async def _ensure_quote(self, token_id, side, price, size, tick_size):
        key = (token_id, side)
        previous = self.last_quotes.get(key)
        if previous:
            old_price, old_size, timestamp = previous
            if abs(old_price - price) < Config.REPRICE_THRESHOLD and time.time() - timestamp < Config.STALE_ORDER_SECONDS:
                return
        try:
            result = await self._call(
                self.client.place_limit_order,
                token_id,
                price,
                size,
                side.lower(),
                tick_size,
            )
            self.last_quotes[key] = (price, size, time.time())
            logger.info("%s quote %s @ %.4f size %.4f -> %s", side, token_id[:10], price, size, result)
        except ValueError as exc:
            logger.info("Quote skipped: %s", exc)

    async def shutdown(self):
        logger.info("Shutting down: canceling open orders")
        try:
            await self._call(self.client.cancel_all_orders)
        except Exception as exc:
            logger.error("Shutdown cancellation failed: %s", exc)
        try:
            await self._notify("🛑 **Polymarket MM Stopped**")
        except Exception:
            pass


def main():
    bot = VolumeBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Stopped by user")


if __name__ == "__main__":
    main()
