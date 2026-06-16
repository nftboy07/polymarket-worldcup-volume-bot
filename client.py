import json
import logging
import requests
from config import Config

# Configure logger
logger = logging.getLogger("PolymarketBot.Client")
logger.setLevel(logging.INFO)

# Try importing py_clob_client_v2 dynamically
# This allows testing the logic and running in simulation/dry-run mode
# even if the heavy library or dependencies fail to install in a sandbox.
try:
    from py_clob_client_v2 import ClobClient, ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions, Side
    CLOB_SDK_AVAILABLE = True
except ImportError:
    CLOB_SDK_AVAILABLE = False
    logger.warning("py_clob_client_v2 not installed. Bot will only support DRY_RUN (simulation) mode.")

class PolymarketClient:
    def __init__(self):
        self.dry_run = Config.DRY_RUN
        self.clob_client = None
        self.authenticated = False
        
        # Configure session with proxy if configured in environment
        self.session = requests.Session()
        # requests automatically picks up HTTP_PROXY and HTTPS_PROXY environment variables.
        
        if not self.dry_run:
            if not CLOB_SDK_AVAILABLE:
                raise ImportError("py-clob-client-v2 must be installed to run in live mode.")
            self._init_clob_client()
        else:
            logger.info("Initializing Polymarket Client in DRY_RUN (simulation) mode.")

    def _init_clob_client(self):
        """Initializes the actual Polymarket CLOB client using PK and API credentials."""
        try:
            logger.info("Initializing CLOB client and L1 authentication...")
            # Initialize with L1 Wallet credentials
            self.clob_client = ClobClient(
                host=Config.CLOB_API_URL, 
                chain_id=137, 
                key=Config.PK
            )
            
            # Derive L2 API credentials if not explicitly provided
            if Config.API_KEY and Config.API_SECRET and Config.API_PASSPHRASE:
                logger.info("Using provided L2 API credentials.")
                creds = ApiCreds(
                    api_key=Config.API_KEY,
                    api_secret=Config.API_SECRET,
                    api_passphrase=Config.API_PASSPHRASE
                )
            else:
                logger.info("Deriving/creating L2 API credentials from wallet signature...")
                raw_creds = self.clob_client.create_or_derive_api_key()
                creds = ApiCreds(
                    api_key=raw_creds.get("apiKey") or raw_creds.get("api_key"),
                    api_secret=raw_creds.get("apiSecret") or raw_creds.get("api_secret"),
                    api_passphrase=raw_creds.get("apiPassphrase") or raw_creds.get("api_passphrase")
                )
            
            # Re-initialize CLOB client with both L1 and L2 authentication
            self.clob_client = ClobClient(
                host=Config.CLOB_API_URL, 
                chain_id=137, 
                key=Config.PK,
                creds=creds
            )
            self.authenticated = True
            logger.info("CLOB Client authenticated successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize CLOB client: {e}")
            raise e

    def fetch_world_cup_markets(self):
        """Fetches active World Cup match markets from the Gamma API."""
        url = f"{Config.GAMMA_API_URL}/public-search?q=World+Cup"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            logger.info("Querying Gamma API for World Cup markets...")
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            search_data = response.json()
            
            markets = []
            events = search_data.get("events") or []
            for event in events:
                if not event.get("active", True):
                    continue
                
                event_title = event.get("title", "")
                logger.info(f"Processing Event: {event_title}")
                
                event_markets = event.get("markets") or []
                for m in event_markets:
                    if not m.get("active", True):
                        continue
                    
                    question = m.get("question", "")
                    clob_token_ids_raw = m.get("clobTokenIds")
                    
                    # clobTokenIds can be a string-encoded JSON array or a python list
                    clob_token_ids = []
                    if isinstance(clob_token_ids_raw, str):
                        try:
                            clob_token_ids = json.loads(clob_token_ids_raw)
                        except json.JSONDecodeError:
                            pass
                    elif isinstance(clob_token_ids_raw, list):
                        clob_token_ids = clob_token_ids_raw
                    
                    # We need at least YES and NO tokens (index 0 and 1)
                    if len(clob_token_ids) >= 2:
                        markets.append({
                            "question": question,
                            "slug": m.get("slug", ""),
                            "yes_token": clob_token_ids[0],
                            "no_token": clob_token_ids[1],
                            "prices": m.get("outcomePrices") or ["0.50", "0.50"]
                        })
            
            logger.info(f"Discovered {len(markets)} active World Cup markets.")
            return markets
            
        except Exception as e:
            logger.warning(f"Error querying Gamma API: {e}.")
            if self.dry_run:
                logger.info("Dry-run fallback: Loading mock World Cup match markets.")
                return self._get_mock_world_cup_markets()
            return []

    def get_midpoint_price(self, token_id):
        """Fetches the current midpoint price of a specific token from the CLOB API."""
        if self.dry_run:
            # Simple mock price simulation
            import random
            return round(0.48 + random.random() * 0.04, 2)
            
        try:
            # Call CLOB API midpoint endpoint
            resp = self.clob_client.get_midpoint(token_id)
            return float(resp.get("midpoint", 0.50))
        except Exception as e:
            logger.error(f"Error getting midpoint price for token {token_id}: {e}")
            raise e

    def get_order_book(self, token_id):
        """Fetches the order book for a specific token."""
        if self.dry_run:
            # Return a mock order book
            return {
                "bids": [{"price": "0.49", "size": "100"}, {"price": "0.48", "size": "200"}],
                "asks": [{"price": "0.51", "size": "150"}, {"price": "0.52", "size": "300"}]
            }
        try:
            return self.clob_client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Error getting order book for token {token_id}: {e}")
            raise e

    def place_limit_order(self, token_id, price, size, side):
        """Places a limit order on the Polymarket CLOB."""
        side_str = "BUY" if side == "buy" or side == Side.BUY else "SELL"
        
        if self.dry_run:
            logger.info(f"[SIMULATION] Placing LIMIT {side_str} order on token {token_id[:10]}... | Price: {price} | Size: {size}")
            return {"status": "SUCCESS", "orderID": "mock-order-id"}
            
        try:
            # Setup order parameters
            clob_side = Side.BUY if side == "buy" else Side.SELL
            resp = self.clob_client.create_and_post_order(
                order_args=OrderArgs(
                    token_id=token_id,
                    price=float(price),
                    side=clob_side,
                    size=float(size)
                ),
                options=PartialCreateOrderOptions(tick_size="0.01"),
                order_type=OrderType.GTC
            )
            logger.info(f"Order placed successfully: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise e

    def cancel_all_orders(self):
        """Cancels all active orders for the authenticated account."""
        if self.dry_run:
            logger.info("[SIMULATION] Canceling all active open orders.")
            return {"status": "SUCCESS"}
            
        try:
            resp = self.clob_client.cancel_all()
            logger.info("All open orders cancelled.")
            return resp
        except Exception as e:
            logger.error(f"Error canceling all orders: {e}")
            raise e

    def get_open_orders(self):
        """Fetches active open orders."""
        if self.dry_run:
            return []
        try:
            # Returns list of open orders from CLOB
            return self.clob_client.get_open_orders()
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []

    def get_position(self, token_id):
        """Fetches current position size in shares for the token."""
        if self.dry_run:
            # Return a mock position
            return 0.0
            
        try:
            # Query on-chain ERC1155 token balance or CLOB positions endpoint
            # In CLOB SDK, we can query our balance for the specific token_id.
            balance_raw = self.clob_client.get_balance(token_id)
            return float(balance_raw.get("balance", 0))
        except Exception as e:
            logger.error(f"Error fetching position for token {token_id}: {e}")
            return 0.0

    def _get_mock_world_cup_markets(self):
        """Returns mock active World Cup matches for dry-run simulation purposes."""
        return [
            {
                "question": "Will Argentina win against France in the World Cup match?",
                "slug": "argentina-vs-france-2026",
                "yes_token": "83471029384729183472918374921873918237492183749218374921837491",
                "no_token": "92837492837492837492837492837492837492837492837492837492837492",
                "prices": ["0.52", "0.48"]
            },
            {
                "question": "Will Brazil score more than 2 goals against Germany?",
                "slug": "brazil-vs-germany-goals",
                "yes_token": "11223344556677889900112233445566778899001122334455667788990011",
                "no_token": "22334455667788990011223344556677889900112233445566778899001122",
                "prices": ["0.45", "0.55"]
            },
            {
                "question": "Will USA qualify for the World Cup quarter-finals?",
                "slug": "usa-qualify-quarters",
                "yes_token": "33445566778899001122334455667788990011223344556677889900112233",
                "no_token": "44556677889900112233445566778899001122334455667788990011223344",
                "prices": ["0.30", "0.70"]
            }
        ]
