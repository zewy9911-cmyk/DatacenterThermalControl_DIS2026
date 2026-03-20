#!/usr/bin/env bash
# =============================================================================
# install.sh — Setup script for Datacenter Thermal Control on Raspberry Pi 5
# Run as: bash install.sh
# =============================================================================
set -euo pipefail

INSTALL_DIR="/home/pi/datacenter_thermal"
VENV="$INSTALL_DIR/venv"
SERVICE="datacenter_thermal.service"

echo "=============================================="
echo "  Datacenter Thermal Control — Installer"
echo "  Raspberry Pi 5"
echo "=============================================="

# Ask whether to install Mosquitto broker on this Pi
echo ""
read -r -p "Install Mosquitto MQTT broker on this Pi? [y/N]: " INSTALL_MOSQUITTO
INSTALL_MOSQUITTO="${INSTALL_MOSQUITTO,,}"   # lowercase

# 1. Update system
echo "[1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv \
     i2c-tools nodejs npm git \
     libgpiod2 python3-libgpiod 2>/dev/null || true

# 2. Mosquitto MQTT broker (optional)
if [[ "$INSTALL_MOSQUITTO" == "y" || "$INSTALL_MOSQUITTO" == "yes" ]]; then
    echo "[2/8] Installing Mosquitto MQTT broker..."
    sudo apt-get install -y mosquitto mosquitto-clients

    # Write a minimal Mosquitto config
    MOSQ_CONF="/etc/mosquitto/conf.d/datacenter.conf"
    sudo tee "$MOSQ_CONF" > /dev/null <<'MOSQ'
# Datacenter Thermal Control — Mosquitto config
listener 1883
allow_anonymous true

# Persistence
persistence true
persistence_location /var/lib/mosquitto/

# Logging
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning
log_type information
MOSQ

    sudo systemctl enable mosquitto
    sudo systemctl restart mosquitto
    BROKER_IP=$(hostname -I | awk '{print $1}')
    echo "  → Mosquitto running on mqtt://${BROKER_IP}:1883"
    echo "  → Edit MQTT_BROKER_HOST in config.py to point other nodes here."
    echo ""
    echo "  Test with:"
    echo "    mosquitto_sub -h localhost -t 'datacenter/#' -v"
    echo "    mosquitto_pub -h localhost -t 'datacenter/test' -m 'hello'"
else
    echo "[2/8] Skipping Mosquitto installation."
    echo "  → Make sure MQTT_BROKER_HOST in config.py points to your broker."
fi

# 3. Enable I2C
echo "[3/8] Enabling I²C interface..."
if ! grep -q "dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
    echo "  → I²C enabled (reboot required)"
else
    echo "  → I²C already enabled"
fi

# 4. Add user to required groups
echo "[4/8] Adding pi to gpio/dialout/i2c groups..."
sudo usermod -aG gpio,dialout,i2c pi 2>/dev/null || true

# 5. Python virtual environment
echo "[5/8] Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r requirements.txt

# 6. Build React UI
echo "[6/8] Building React dashboard..."
cd "$INSTALL_DIR/GUI"
npm install --silent
npm run build
cd "$INSTALL_DIR"

# 7. Create storage directory
echo "[7/8] Creating storage directory..."
mkdir -p "$INSTALL_DIR/Storage"
chmod 755 "$INSTALL_DIR/Storage"

# 8. Install systemd service
echo "[8/8] Installing systemd service..."
sudo cp "$INSTALL_DIR/$SERVICE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl start  "$SERVICE"

echo ""
echo "=============================================="
echo "  Installation complete!"
echo ""
MYIP=$(hostname -I | awk '{print $1}')
echo "  Web UI:   http://${MYIP}:8000"
echo "  API docs: http://${MYIP}:8000/docs"
if [[ "$INSTALL_MOSQUITTO" == "y" || "$INSTALL_MOSQUITTO" == "yes" ]]; then
echo "  MQTT:     mqtt://${MYIP}:1883"
fi
echo ""
echo "  Commands:"
echo "    sudo systemctl status  datacenter_thermal"
echo "    sudo systemctl restart datacenter_thermal"
echo "    journalctl -u datacenter_thermal -f"
echo ""
echo "  GPIO pin map (BCM):"
echo "    GPIO  4 — DHT22 data (if using DHT22)"
echo "    GPIO 17 — Status LED (green, heartbeat)"
echo "    GPIO 27 — Alarm LED  (red, alert)"
echo "    GPIO 22 — Mode button (toggle AUTO/MANUAL)"
echo "    GPIO 23 — Fan tachometer input"
echo "    GPIO 24 — Valve 1 feedback"
echo "    GPIO 25 — Valve 2 feedback"
echo ""
echo "  ⚠  A reboot is required to activate I²C."
echo "     Run: sudo reboot"
echo "=============================================="

# =============================================================================
# install.sh — Setup script for Datacenter Thermal Control on Raspberry Pi 5
# Run as: bash install.sh
# =============================================================================
set -euo pipefail

INSTALL_DIR="/home/pi/datacenter_thermal"
VENV="$INSTALL_DIR/venv"
SERVICE="datacenter_thermal.service"

echo "=============================================="
echo "  Datacenter Thermal Control — Installer"
echo "  Raspberry Pi 5"
echo "=============================================="

# 1. Update system
echo "[1/7] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv \
     i2c-tools nodejs npm git \
     libgpiod2 python3-libgpiod 2>/dev/null || true

# 2. Enable I2C
echo "[2/7] Enabling I²C interface..."
if ! grep -q "dtparam=i2c_arm=on" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/firmware/config.txt
    echo "  → I²C enabled (reboot required)"
else
    echo "  → I²C already enabled"
fi

# 3. Add user to required groups
echo "[3/7] Adding pi to gpio/dialout/i2c groups..."
sudo usermod -aG gpio,dialout,i2c pi 2>/dev/null || true

# 4. Python virtual environment
echo "[4/7] Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r requirements.txt

# 5. Build React UI
echo "[5/7] Building React dashboard..."
cd "$INSTALL_DIR/GUI"
npm install --silent
npm run build
cd "$INSTALL_DIR"

# 6. Create storage directory
echo "[6/7] Creating storage directory..."
mkdir -p "$INSTALL_DIR/Storage"
chmod 755 "$INSTALL_DIR/Storage"

# 7. Install systemd service
echo "[7/7] Installing systemd service..."
sudo cp "$INSTALL_DIR/$SERVICE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl start  "$SERVICE"

echo ""
echo "=============================================="
echo "  Installation complete!"
echo ""
echo "  Web UI:   http://$(hostname -I | awk '{print $1}'):8000"
echo "  API docs: http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "  Commands:"
echo "    sudo systemctl status  datacenter_thermal"
echo "    sudo systemctl restart datacenter_thermal"
echo "    journalctl -u datacenter_thermal -f"
echo ""
echo "  ⚠  A reboot is required to activate I²C."
echo "     Run: sudo reboot"
echo "=============================================="

