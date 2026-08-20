import json
import logging
import time
from decimal import Decimal, ROUND_DOWN
import requests
from config import Config

logger = logging.getLogger("PolymarketBot.Client")

try:
    from py_clob_client_v2 import (
        ClobClient, ApiCreds, OrderArgs, OrderType,
        PartialCreateOrderOptions, Side, BalanceAllowanceParams, AssetType
    )
    CLOB_SDK_AVAILABLE = True
except ImportError:
    CLOB_SDK_AVAILABLE = False


class PolymarketClient:
    def __init__(self):
        self.dry_run = Config.DRY_RUN
        self.clob_client = None
        self.authenticated = False
        self.session = requests.Session()
        self.market_rules = {}
        self._market_rules_ttl = 300
        self._last_rules_refresh = {}
        self._init_lock = False
        if not self.dry_run:
            if not CLOB_SDK_AVAILABLE:
                raise ImportError("py-clob-client-v2 is required when DRY_RUN=false")
            self._init_clob_client()

    def _init_clob_client(self):
        self.clob_client = ClobClient(
            host=Config.CLOB_API_URL,
            chain_id=137,
            key=Config.PK,
            signature_type=Config.SIGNATURE_TYPE,
            funder=Config.FUNDER,
        )
        if Config.API_KEY and Config.API_SECRET and Config.API_PASSPHRASE:
            creds = ApiCreds(
                api_key=Config.API_KEY,
                api_secret=Config.API_SECRET,
                api_passphrase=Config.API_PASSPHRASE,
            )
        else:
            raw = self.clob_client.create_or_derive_api_key()
            if hasattr(raw, "api_key"):
                creds = raw
            else:
                creds = ApiCreds(
                    api_key=raw.get("apiKey") or raw.get("api_key"),
                    api_secret=raw.get("apiSecret") or raw.get("api_secret"),
                    api_passphrase=raw.get("apiPassphrase") or raw.get("api_passphrase"),
                )
        self.clob_client = ClobClient(
            host=Config.CLOB_API_URL,
            chain_id=137,
            key=Config.PK,
            creds=creds,
            signature_type=Config.SIGNATURE_TYPE,
            funder=Config.FUNDER,
        )
        self.authenticated = True

    @staticmethod
    def _parse_token_ids(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        return value if isinstance(value, list) else []

    def fetch_world_cup_markets(self):
        url = f"{Config.GAMMA_API_URL}/public-search"
        try:
            response = self.session.get(
                url,
                params={"q": "World Cup"},
                headers={"User-Agent": "PolymarketMM/2.0"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            markets = []
            for event in data.get("events") or []:
                if event.get("closed") or event.get("active") is False:
                    continue
                for market in event.get("markets") or []:
                    if market.get("closed") or market.get("active") is False:
                        continue
                    tokens = self._parse_token_ids(market.get("clobTokenIds"))
                    if len(tokens) < 2:
                        continue
                    prices = market.get("outcomePrices") or []
                    try:
                        yes_price = float(prices[0]) if prices else 0.5
                    except (ValueError, TypeError):
                        yes_price = 0.5
                    markets.append({
                        "question": market.get("question") or event.get("title") or "Unknown",
                        "slug": market.get("slug", ""),
                        "yes_token": tokens[0],
                        "no_token": tokens[1],
                        "prices": [yes_price, max(0.0, 1.0 - yes_price)],
                        "active": True,
                        "end_date": market.get("endDate") or event.get("endDate"),
                        "liquidity": float(market.get("liquidity") or 0),
                        "neg_risk": bool(market.get("negRisk", False)),
                    })
            markets.sort(key=lambda m: m["liquidity"], reverse=True)
            return markets[: Config.MAX_MARKETS]
        except Exception as exc:
            logger.error("Market discovery failed: %s", exc)
            if self.dry_run:
                return self._get_mock_world_cup_markets()
            raise RuntimeError(f"Market discovery failed: {exc}") from exc

    def get_order_book(self, token_id):
        if self.dry_run:
            return {"bids": [{"price": "0.49", "size": "100"}], "asks": [{"price": "0.51", "size": "100"}]}
        return self.clob_client.get_order_book(token_id)

    @staticmethod
    def _levels(book, side):
        raw = book.get(side) if isinstance(book, dict) else getattr(book, side, None)
        return raw or []

    @staticmethod
    def _level_value(level, key):
        if isinstance(level, dict):
            return float(level[key])
        return float(getattr(level, key))

    def quote_from_book(self, token_id):
        book = self.get_order_book(token_id)
        bids = self._levels(book, "bids")
        asks = self._levels(book, "asks")
        if not bids or not asks:
            raise RuntimeError("Order book has no two-sided liquidity")
        best_bid = max(self._level_value(x, "price") for x in bids)
        best_ask = min(self._level_value(x, "price") for x in asks)
        if not (0 < best_bid < best_ask < 1):
            raise RuntimeError(f"Invalid book: bid={best_bid}, ask={best_ask}")
        return best_bid, best_ask, (best_bid + best_ask) / 2.0

    def get_market_rules(self, token_id, fallback_tick=0.01):
        now = time.time()
        cached = self.market_rules.get(token_id)
        if cached and now - self._last_rules_refresh.get(token_id, 0) < self._market_rules_ttl:
            return cached
        tick = fallback_tick
        min_size = 5.0
        if not self.dry_run:
            # The SDK/API can differ by installed V2 version, so probe safely.
            try:
                getter = getattr(self.clob_client, "get_tick_size", None)
                if getter:
                    tick = float(getter(token_id))
            except Exception:
                pass
            try:
                getter = getattr(self.clob_client, "get_min_order_size", None)
                if getter:
                    min_size = float(getter(token_id))
            except Exception:
                pass
            try:
                response = self.session.get(
                    f"{Config.CLOB_API_URL}/tick-size",
                    params={"token_id": token_id},
                    timeout=5,
                )
                if response.ok:
                    payload = response.json()
                    tick = float(payload.get("minimum_tick_size", payload.get("tick_size", tick)))
            except Exception:
                pass
        if tick <= 0:
            tick = fallback_tick
        self.market_rules[token_id] = {"tick_size": tick, "min_size": min_size}
        self._last_rules_refresh[token_id] = now
        return self.market_rules[token_id]

    @staticmethod
    def round_price(price, tick_size):
        tick = Decimal(str(tick_size))
        value = (Decimal(str(price)) / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        return float(max(Decimal("0.01"), min(Decimal("0.99"), value)))

    def place_limit_order(self, token_id, price, size, side, tick_size=0.01, post_only=False):
        price = self.round_price(price, tick_size)
        size = float(size)
        if size <= 0:
            raise ValueError("Order size must be positive")
        rules = self.get_market_rules(token_id, tick_size)
        if size < rules["min_size"]:
            raise ValueError(f"Order size {size} is below market minimum {rules['min_size']}")
        if self.dry_run:
            return {"status": "SIMULATED", "orderID": f"dry-{token_id[:8]}-{int(time.time()*1000)}"}
        clob_side = Side.BUY if str(side).lower() == "buy" else Side.SELL
        options = PartialCreateOrderOptions(tick_size=str(rules["tick_size"]))
        # Keep the SDK-compatible path conservative; do not invent unsupported kwargs.
        return self.clob_client.create_and_post_order(
            order_args=OrderArgs(token_id=token_id, price=price, side=clob_side, size=size),
            options=options,
            order_type=OrderType.GTC,
        )

    def cancel_order(self, order_id):
        if self.dry_run:
            return {"status": "SIMULATED"}
        cancel = getattr(self.clob_client, "cancel", None)
        if not cancel:
            raise RuntimeError("Installed CLOB SDK does not expose single-order cancellation")
        return cancel(order_id)

    def cancel_all_orders(self):
        if self.dry_run:
            return {"status": "SIMULATED"}
        return self.clob_client.cancel_all()

    def get_open_orders(self):
        if self.dry_run:
            return []
        return self.clob_client.get_open_orders()

    def get_position(self, token_id):
        if self.dry_run:
            return 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            raw = self.clob_client.get_balance_allowance(params)
            return float(raw.get("balance", 0.0))
        except Exception as exc:
            # Never convert an unknown account state into zero exposure.
            raise RuntimeError(f"Position lookup failed for {token_id}: {exc}") from exc

    def _get_mock_world_cup_markets(self):
        return [{
            "question": "SIMULATION: World Cup market",
            "slug": "simulation-market",
            "yes_token": "SIM_YES",
            "no_token": "SIM_NO",
            "prices": [0.50, 0.50],
            "active": True,
            "liquidity": 1000.0,
            "neg_risk": False,
        }]
