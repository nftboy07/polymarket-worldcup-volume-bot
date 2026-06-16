#!/bin/bash
set -e

# Polymarket Volume Bot VPS Deploy Script
# Targets: Ubuntu / Debian

echo "=================================================="
echo " Starting Polymarket Bot Deployment on VPS"
echo "=================================================="

# 1. Update package list and install system dependencies
echo ">>> Checking and installing system dependencies..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git

# 2. Create Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ">>> Creating Python virtual environment..."
    python3 -m venv venv
else
    echo ">>> Virtual environment already exists."
fi

# 3. Activate virtual environment and install dependencies
echo ">>> Installing python requirements..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Check for .env file configuration
if [ ! -f ".env" ]; then
    echo ">>> Creating .env file from template..."
    cp .env.example .env
    echo "=================================================="
    echo " WARNING: .env file created from template."
    echo " Please configure your credentials (PK, Telegram tokens, etc.)"
    echo " by running: nano .env"
    echo "=================================================="
else
    echo ">>> .env file already exists. Skipping copy."
fi

# 5. systemd Service Setup Instructions
echo ">>> Setting up systemd background service configuration..."
echo "To make the bot run permanently in the background, run the following commands:"
echo ""
echo "  # Copy the service configuration to systemd"
echo "  sudo cp polymarket-bot.service /etc/systemd/system/polymarket-bot.service"
echo ""
echo "  # Reload systemd configuration"
echo "  sudo systemctl daemon-reload"
echo ""
echo "  # Enable the service to start automatically on boot"
echo "  sudo systemctl enable polymarket-bot.service"
echo ""
echo "  # Start the service"
echo "  sudo systemctl start polymarket-bot.service"
echo ""
echo "  # Check bot status and logs"
echo "  sudo systemctl status polymarket-bot.service"
echo "  sudo journalctl -u polymarket-bot.service -f -n 50"
echo ""
echo "=================================================="
echo " Deployment Script Complete!"
echo "=================================================="
