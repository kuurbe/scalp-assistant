#!/bin/bash
# ──────────────────────────────────────────────────────
# Scalp Assistant — Oracle Cloud Deploy Script
# Run this ONCE after SSH-ing into your VM:
#   chmod +x scripts/deploy.sh && ./scripts/deploy.sh
# ──────────────────────────────────────────────────────

set -e

echo "═══════════════════════════════════════════"
echo "  Scalp Assistant v5 — Cloud Deploy"
echo "═══════════════════════════════════════════"

# 1. Install Python + deps
echo "→ Installing Python & system deps..."
if command -v dnf &>/dev/null; then
    sudo dnf install -y python3 python3-pip git
elif command -v apt &>/dev/null; then
    sudo apt update && sudo apt install -y python3 python3-pip git
fi

# 2. Install Python packages
echo "→ Installing Python packages..."
pip3 install --user -r requirements.txt

# 3. Setup .env if not exists
if [ ! -f .env ]; then
    echo "→ Creating .env from template..."
    cp .env.example .env
    echo "⚠️  EDIT .env with your API keys: nano .env"
    exit 1
fi

# 4. Test the scanner
echo "→ Testing scanner..."
python3 -m scripts.live_scanner --test
echo "✅ Test alert sent — check your Telegram!"

# 5. Create systemd service
echo "→ Creating systemd service..."
WORKDIR=$(pwd)
PYTHON=$(which python3)

sudo tee /etc/systemd/system/scalp-assistant.service > /dev/null <<SVCEOF
[Unit]
Description=Scalp Assistant Live Scanner
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$WORKDIR
ExecStart=$PYTHON -m scripts.live_scanner --interval 15
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Env vars from .env
EnvironmentFile=$WORKDIR/.env

[Install]
WantedBy=multi-user.target
SVCEOF

# 6. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable scalp-assistant
sudo systemctl start scalp-assistant

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ DEPLOYED! Scanner is running 24/7"
echo "═══════════════════════════════════════════"
echo ""
echo "  Commands:"
echo "    sudo systemctl status scalp-assistant   # check status"
echo "    sudo journalctl -u scalp-assistant -f   # live logs"
echo "    sudo systemctl restart scalp-assistant   # restart"
echo "    sudo systemctl stop scalp-assistant      # stop"
echo ""
