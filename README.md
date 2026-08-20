# Polymarket World Cup Market Maker

A hardened Python market-making bot for Polymarket World Cup markets. The live path is intentionally limited to passive, post-only GTC quoting; the previous instant YES/NO offset mode has been removed.

## What changed

- Uses live two-sided order books instead of midpoint-only pricing.
- Uses market tick-size metadata and Decimal rounding.
- Passes market `negRisk` into order construction.
- Uses post-only GTC orders to avoid accidental taker execution.
- Does not call `cancel_all_orders()` every polling cycle.
- Cancels stale individual orders when the SDK exposes single-order cancellation.
- Enforces maximum position, total exposure, open-order, market-count, liquidity and spread limits.
- Fails closed when position/account state cannot be read.
- Uses `asyncio.to_thread()` around blocking HTTP/CLOB calls so the event loop is not blocked.
- Stops after repeated failures and cancels outstanding orders.
- Runs with `DRY_RUN=true` by default.
- Adds unit tests for price rounding and invalid order books.
- Systemd uses `Restart=on-failure` instead of restarting after a deliberate clean stop.

## Important live-trading note

The code cannot guarantee that every Polymarket account flow can place orders through the installed Python CLOB SDK. Deposit/proxy wallet authentication has had SDK/API compatibility issues, so the first live test must be performed with a very small amount and verified against the account's actual signature type and funder configuration.

## Configuration

Copy `.env.example` to `.env` and keep `DRY_RUN=true` until the bot has passed your environment checks.

Key controls:

```env
DRY_RUN=true
STRATEGY=market_making
ORDER_SIZE=5.0
SPREAD=0.02
MAX_POSITION=50.0
MAX_TOTAL_EXPOSURE=100.0
MAX_OPEN_ORDERS=20
MAX_MARKETS=10
MIN_LIQUIDITY=10.0
MAX_SPREAD=0.20
STALE_ORDER_SECONDS=30
REPRICE_THRESHOLD=0.01
MAX_CONSECUTIVE_ERRORS=5
POLL_INTERVAL=2.0
```

For deposit-wallet accounts, configure the correct `SIGNATURE_TYPE` and `FUNDER` values for your account. Do not commit the private key or API credentials.

## Test

```bash
python -m unittest discover -s tests -v
```

## Run

```bash
python bot.py
```

## Strategy

The bot reads the real CLOB order book, checks liquidity and spread, calculates passive quotes, and places post-only GTC orders. Inventory is reduced with passive asks when shares are held. The bot does not use market orders and does not intentionally generate artificial matched volume.

## VPS

The included systemd unit assumes:

```text
/home/ubuntu/polymarket-worldcup-volume-bot
```

and a virtual environment at:

```text
/home/ubuntu/polymarket-worldcup-volume-bot/venv
```

Review the `User`, paths and `.env` location before enabling the service.

## Disclaimer

Automated prediction-market trading carries financial risk. This project is designed for legitimate liquidity provision and testing. Do not use it to create artificial or wash volume, and verify Polymarket's current rules before live deployment.
