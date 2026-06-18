# Polymarket World Cup Volume Farming Bot

A robust, production-ready Python bot designed to farm trading volume on Polymarket during the FIFA World Cup. It targets World Cup matches dynamically or selectively, and supports two primary strategies: **Dual-Buy Market Making** and **Yes/No Offsetting**.

> [!IMPORTANT]
> **Polymarket Geo-Blocking**: Polymarket blocks IP addresses from the United States and several other countries. If you run the bot from a restricted region, you **must** configure an outbound proxy. The bot's underlying libraries (`requests` and `web3`) will automatically respect standard system/process proxy variables (`HTTP_PROXY` and `HTTPS_PROXY`).

---

## Features

- **Dynamic Discovery**: Query the Polymarket Gamma API to search for active FIFA World Cup matches on-the-fly.
- **Dual-Buy Market Making Strategy**: Places limit buy orders for YES and NO outcomes around the midpoint price to capture the spread risk-neutrally (does not require holding initial shares).
- **Yes/No Offsetting Strategy**: Executes market/tight-limit orders on both YES and NO outcomes simultaneously to lock in instant volume with zero price exposure.
- **Safety Measures**:
  - `DRY_RUN` mode enabled by default to simulate placing orders without actual capital risk.
  - `MAX_POSITION` threshold prevents the bot from accumulating too many shares of one side.
  - Automatic order cancellation on exit and startup.
- **Robustness**: Handles network timeouts gracefully, falling back to simulated data in dry-run mode.

---

## Project Structure

```
├── bot.py                # Main entry point and orchestration loop
├── client.py             # Wrapper around Gamma API and py-clob-client-v2
├── config.py             # Environment configuration validation and loader
├── requirements.txt      # Python dependencies
├── tests/
│   └── test_bot.py       # Unit test suite verifying all modules in dry-run
└── README.md             # Project documentation
```

---

## Installation

1. **Clone the repository** (or download the files).
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: If you are using Windows and encounter dependency build errors, ensure you have Python 3.8+ and C++ Build Tools installed.*

---

## Configuration

Create a `.env` file in the root directory of the project. You can copy the template below:

```env
# --- WALLET & API CREDENTIALS ---
# Your Ethereum wallet private key (Polygon network)
PK=0x...

# RPC URL for the Polygon network (defaults to https://polygon-rpc.com)
RPC_URL=https://polygon-rpc.com

# (Optional) If you already have Polymarket API credentials, provide them here.
# If left blank, they will be derived automatically using your wallet signature (L1 auth).
API_KEY=
API_SECRET=
API_PASSPHRASE=

# --- DEPOSIT WALLET FLOW (REQUIRED for most Polymarket accounts) ---
# Polymarket now requires deposit wallet flow for most users.
# SIGNATURE_TYPE=3 (POLY_1271) is required for deposit wallets.
# FUNDER = your deposit wallet address from your Polymarket profile.
SIGNATURE_TYPE=3
FUNDER=0x...

# --- BOT SETTINGS ---
# Mode: "true" to simulate, "false" to execute live orders
DRY_RUN=true

# Strategy: "market_making" (recommended) or "yes_no_offset"
STRATEGY=market_making

# Order size in USDC per order (Polymarket has a minimum of $1 / 5 shares)
ORDER_SIZE=5.0

# Bid-Ask spread around midpoint (e.g., 0.02 is 2 cents spread)
SPREAD=0.02

# Maximum inventory limit in shares. Bot pauses bidding if threshold is hit.
MAX_POSITION=50.0

# Polling frequency in seconds
POLL_INTERVAL=10

# --- TELEGRAM NOTIFICATIONS (Optional) ---
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

### Running with a Proxy

To run the bot through a proxy (e.g. SOCKS5 or HTTP proxy in Europe/Asia), set the environment variables in your terminal session before starting the bot:

**On Windows (PowerShell):**
```powershell
$env:HTTP_PROXY="http://your-proxy-address:port"
$env:HTTPS_PROXY="http://your-proxy-address:port"
python bot.py
```

**On Linux / macOS:**
```bash
export HTTP_PROXY="http://your-proxy-address:port"
export HTTPS_PROXY="http://your-proxy-address:port"
python bot.py
```

---

## Deposit Wallet Flow (Required for Live Trading)

Polymarket now requires the **deposit wallet flow** for most accounts. If you see the error `maker address not allowed, please use the deposit wallet flow`, you must configure:

1. Go to your **Polymarket Profile** → copy your **Deposit Wallet** address.
2. Add to your `.env`:
   ```env
   SIGNATURE_TYPE=3
   FUNDER=0xYourDepositWalletAddress
   ```
3. Restart the bot.

> **Note:** `SIGNATURE_TYPE=3` (POLY_1271) tells the CLOB SDK to sign orders using the deposit wallet instead of your raw EOA. Without this, every order will be rejected with a 400 error.

---

## Usage

### Run Tests
To verify everything is working locally:
```bash
python -m unittest discover -s tests
```

### Run Bot
To start the bot:
```bash
python bot.py
```

---

## Strategies Explained

### 1. Dual-Buy Market Making (Recommended)
This strategy acts as a passive liquidity provider. Since predicting match outcomes carries risk, the bot places limit buys on **both YES and NO** outcomes:
1. Fetches midpoint price $M$ for the YES token.
2. Places a limit buy for YES at $M - (\text{spread}/2)$.
3. Places a limit buy for NO at $(1.0 - M) - (\text{spread}/2)$.
4. Since they are both buy orders, you only need USDC to start.
5. Once they fill, the bot holds offset YES and NO positions (neutral risk).
6. The bot will then attempt to place limit sells (asks) at $M + (\text{spread}/2)$ to exit the positions and capture the spread.

### 2. Yes/No Offsetting
For rapid volume accumulation:
1. Immediately places buy orders on both YES and NO outcomes for the same market at current midpoint prices.
2. Since YES + NO always equals $1.00, your portfolio remains perfectly hedged.
3. This strategy is faster but subject to bid-ask slippage.

---

## Automated Deployment (GitHub Actions)

This repository includes a GitHub Actions workflow that automatically deploys the bot to your VPS on every push to the `main` branch. 

### Setup Instructions

1. **Configure Repository Secrets on GitHub**:
   - Go to your repository on GitHub.
   - Navigate to **Settings -> Secrets and variables -> Actions**.
   - Click **New repository secret** and add the following:
     - `VPS_HOST`: Your VPS public IP address (e.g., `123.45.67.89`).
     - `VPS_USERNAME`: The SSH login user (e.g., `ubuntu` or `root`).
     - `VPS_SSH_KEY`: The contents of your private SSH key (e.g., `id_rsa`) that has authorization to access your VPS.
     - `VPS_PASSWORD` *(Alternative)*: If you do not use SSH keys, configure this with your SSH login password instead.
     - `ENV_CONTENT`: The complete contents of your configured `.env` file (e.g., wallet private key `PK`, Telegram credentials, dry-run flags).

2. **Triggering Deployment**:
   - Whenever you push code changes to the `main` branch, the workflow will trigger.
   - It will automatically establish an SSH connection to your VPS, pull the latest code, write your secrets to `.env`, set up the virtual environment, and start/restart the background `systemd` daemon.

---

## Disclaimer

This bot is for educational purposes only. Automated trading on prediction markets involves financial risk. Wash trading or collusive volume manipulation is against Polymarket's Market Integrity rules and could result in account restriction. Use responsibly.

