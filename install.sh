#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
LAUNCHER="$HOME/.local/bin/voice-input"
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/voice-input.service"

echo "=== voice-input installer ==="
echo ""

# -----------------------------------------------------------------------
# 1. System packages
# -----------------------------------------------------------------------
echo "[1/6] Installing system packages..."
sudo apt install -y wl-clipboard wtype libportaudio2 python3-venv

# -----------------------------------------------------------------------
# 2. Input group (for evdev access to /dev/input/*)
# -----------------------------------------------------------------------
if groups "$USER" | grep -qw input; then
    echo "[2/6] User '$USER' is already in the 'input' group."
else
    echo "[2/6] Adding '$USER' to the 'input' group..."
    sudo usermod -aG input "$USER"
    echo "  *** You must log out and back in for this to take effect. ***"
fi

# -----------------------------------------------------------------------
# 3. Python venv + packages
# -----------------------------------------------------------------------
echo "[3/6] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
echo "  Installing Python packages (this may take a minute)..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
echo "  Done."

# -----------------------------------------------------------------------
# 4. Generate sound cues
# -----------------------------------------------------------------------
echo "[4/6] Generating audio cues..."
"$VENV_DIR/bin/python" "$SCRIPT_DIR/voice-input.py" --generate-sounds

# -----------------------------------------------------------------------
# 5. Launcher script
# -----------------------------------------------------------------------
echo "[5/6] Installing launcher at $LAUNCHER..."
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LAUNCHER_EOF

# Append the resolved path (not a variable that would expand at runtime)
cat >> "$LAUNCHER" << EOF
VOICE_INPUT_DIR="$SCRIPT_DIR"
EOF

cat >> "$LAUNCHER" << 'LAUNCHER_EOF'
exec "$VOICE_INPUT_DIR/venv/bin/python" "$VOICE_INPUT_DIR/voice-input.py" "$@"
LAUNCHER_EOF

chmod +x "$LAUNCHER"

# -----------------------------------------------------------------------
# 6. Systemd user service
# -----------------------------------------------------------------------
echo "[6/6] Installing systemd user service..."
mkdir -p "$SERVICE_DIR"
WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Voice Input — hold-to-speak speech-to-text daemon
After=graphical-session.target

[Service]
Type=simple
Environment=WAYLAND_DISPLAY=$WAYLAND_DISPLAY
ExecStart=$VENV_DIR/bin/python $SCRIPT_DIR/voice-input.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable voice-input.service
echo "  Service installed. Start with: systemctl --user start voice-input"

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
if ! groups "$USER" | grep -qw input; then
    echo "  1. LOG OUT and back in (for 'input' group membership)"
    echo "  2. Start the daemon:  voice-input"
    echo "     Or:                systemctl --user start voice-input"
else
    echo "  1. Start the daemon:  voice-input"
    echo "     Or:                systemctl --user start voice-input"
fi
echo ""
echo "  Hold Ctrl+Super to record, release to transcribe."
echo "  Tap Ctrl+Super+Shift to toggle LLM cleanup."
echo ""
echo "  Edit settings: $SCRIPT_DIR/settings.json"
echo "  See defaults:  $SCRIPT_DIR/settings.defaults.json"
