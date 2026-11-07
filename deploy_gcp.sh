#!/usr/bin/env bash
# ==============================================================================
# GCP Free Tier (e2-micro) Automated One-Click Provisioner & Deployment Script
# Pod 1: India Growth Equities (NSE 100) | Pod 2: US Growth Equities (NASDAQ/NYSE 100)
# ==============================================================================

set -euo pipefail

echo "======================================================================"
echo "    AUTONOMOUS DUAL-POD BOT - GCP FREE TIER PROVISIONER (e2-micro)    "
echo "======================================================================"

# 1. ROOT CHECK / SUDO HELPER
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "[-] Error: Please run as root or install sudo."
        exit 1
    fi
fi

# 2. CONFIGURE 2GB SWAP FILE (CRITICAL FOR 1GB RAM e2-micro INSTANCES)
if ! swapon --show | grep -q "/swapfile"; then
    echo "[+] Configuring 2GB Swap space to protect 1GB RAM against OOM killer..."
    $SUDO fallocate -l 2G /swapfile || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048
    $SUDO chmod 600 /swapfile
    $SUDO mkswap /swapfile
    $SUDO swapon /swapfile
    if ! grep -q "/swapfile" /etc/fstab; then
        echo "/swapfile none swap sw 0 0" | $SUDO tee -a /etc/fstab
    fi
    echo "[+] 2GB Swapfile activated successfully."
else
    echo "[*] Swapfile already active."
fi

# 3. INSTALL SYSTEM DEPENDENCIES
echo "[+] Updating apt repositories and installing core packages..."
$SUDO apt-get update -y
$SUDO apt-get install -y python3 python3-pip python3-venv git curl build-essential tzdata

# 4. DETERMINE PROJECT DIRECTORY
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CURRENT_USER="$(whoami)"

echo "[*] Project directory: ${PROJECT_ROOT}"
echo "[*] Operating user: ${CURRENT_USER}"

# 5. SETUP PYTHON VIRTUAL ENVIRONMENT
if [ ! -d "${PROJECT_ROOT}/venv" ]; then
    echo "[+] Creating Python virtual environment in ${PROJECT_ROOT}/venv..."
    python3 -m venv "${PROJECT_ROOT}/venv"
fi

echo "[+] Upgrading pip and installing wheels..."
"${PROJECT_ROOT}/venv/bin/pip" install --upgrade pip setuptools wheel

echo "[+] Installing project requirements..."
"${PROJECT_ROOT}/venv/bin/pip" install -r "${PROJECT_ROOT}/requirements.txt"

# 6. SETUP .env CONFIGURATION
if [ ! -f "${PROJECT_ROOT}/.env" ]; then
    echo "[+] Creating .env configuration from template..."
    if [ -f "${PROJECT_ROOT}/.env.example" ]; then
        cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
    else
        cat <<EOF > "${PROJECT_ROOT}/.env"
ENVIRONMENT=production
ALPACA_LIVE=0
PAPER_API_KEY=your_alpaca_key_here
PAPER_API_SECRET=your_alpaca_secret_here
GROWW_FALLBACK_ACTIVE=1
EOF
    fi
    echo "[!] NOTE: Update your Alpaca API credentials in ${PROJECT_ROOT}/.env"
fi

# 7. GENERATE SYSTEMD SERVICE
echo "[+] Configuring systemd daemon service (quant-bot)..."
SERVICE_FILE="/etc/systemd/system/quant-bot.service"
TEMP_SERVICE="/tmp/quant-bot.service"

sed -e "s|%USER%|${CURRENT_USER}|g" \
    -e "s|%WORKING_DIR%|${PROJECT_ROOT}|g" \
    "${PROJECT_ROOT}/trading_system/scripts/quant-bot.service" > "${TEMP_SERVICE}"

$SUDO mv "${TEMP_SERVICE}" "${SERVICE_FILE}"
$SUDO chmod 644 "${SERVICE_FILE}"

echo "[+] Reloading systemd and enabling service..."
$SUDO systemctl daemon-reload
$SUDO systemctl enable quant-bot.service
$SUDO systemctl restart quant-bot.service

echo ""
echo "======================================================================"
echo "[SUCCESS] QUANT-BOT DAEMON IS ACTIVE AND RUNNING 24/7 IN THE CLOUD!"
echo "======================================================================"
echo "Check live status:    sudo systemctl status quant-bot"
echo "Follow live logs:     journalctl -u quant-bot -f"
echo "Or check bot log:     tail -f ${PROJECT_ROOT}/trading_system/data/cloud_daemon.log"
echo "======================================================================"
