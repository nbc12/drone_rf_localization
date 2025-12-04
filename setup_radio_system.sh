#!/bin/bash

# =================================================================
# MASTER INSTALLER: GNU RADIO + BLADERF + GR-AOA (CUSTOM MODULE)
# =================================================================
# This script sets up the entire environment for the Direction Finding project.
#
# Usage: sudo ./setup_radio_system.sh
#
# POLICY: All source code and downloaded files remain in the script's directory.
#         Only final binaries and libraries are installed system-wide.
# =================================================================

# --- CONFIGURATION ---
FIRMWARE_URL="https://www.nuand.com/fpga/v0.15.3/hostedxA4.rbf"

# Exit on error
set -e

# --- PRE-FLIGHT CHECKS ---

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Error: This script must be run with sudo."
    exit 1
fi

# Determine the actual user (not root) to fix file ownership later
ORIGINAL_USER="${SUDO_USER:-$(whoami)}"
ORIGINAL_HOME=$(getent passwd "$ORIGINAL_USER" | cut -d: -f6)

# DETERMINE WORKING DIRECTORY
# This ensures we install everything alongside the script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

if [ -z "$ORIGINAL_HOME" ]; then
    echo "❌ Error: Could not determine home directory."
    exit 1
fi

echo "==================================================="
echo "🚀 STARTING RADIO SYSTEM SETUP"
echo "   User:      $ORIGINAL_USER"
echo "   Work Dir:  $SCRIPT_DIR"
echo "==================================================="

# --- 1. SYSTEM DEPENDENCIES ---
echo "📦 [1/7] Installing System Dependencies..."
apt-get update -qq

DEPS=(
    "git" "cmake" "build-essential" "wget"
    "gnuradio" "gnuradio-dev" "gr-osmosdr"
    "libbladerf-dev" "libbladerf2" "libgtk-3-dev"
    "python3-serial" "python3-numpy" "python3-setuptools"
    "linux-tools-virtual" "hwdata"
)

apt-get install -y "${DEPS[@]}"

# --- 2. BLADERF FIRMWARE ---
echo "💾 [2/7] Setting up BladeRF Firmware..."
FIRMWARE_FILENAME=$(basename "$FIRMWARE_URL")
FIRMWARE_PATH="$SCRIPT_DIR/$FIRMWARE_FILENAME"

if [ -f "$FIRMWARE_PATH" ]; then
    echo "   Firmware already exists in working dir. Skipping download."
else
    echo "   Downloading firmware to $SCRIPT_DIR..."
    wget --no-verbose -P "$SCRIPT_DIR" "$FIRMWARE_URL"
    chown "$ORIGINAL_USER:$ORIGINAL_USER" "$FIRMWARE_PATH"
fi

# --- 3. BLADERF UDEV RULES ---
echo "🔑 [3/7] Configuring Udev Rules..."
RULES_FILE="/etc/udev/rules.d/88-nuand.rules"

if [ -f "$RULES_FILE" ]; then
    echo "   Rules file exists. Skipping."
else
    echo "   Creating udev rules..."
    tee "$RULES_FILE" > /dev/null <<EOF
# bladeRF 1.0 (fx3)
ATTRS{idVendor}=="2cf0", ATTRS{idProduct}=="5250", MODE="0660", GROUP="plugdev"
# bladeRF 2.0 micro (fx3)
ATTRS{idVendor}=="2cf0", ATTRS{idProduct}=="525a", MODE="0660", GROUP="plugdev"
EOF
    chmod 644 "$RULES_FILE"
    udevadm control --reload-rules
    udevadm trigger
fi

# --- 4. INSTALL GR-BLADERF (OOT) ---
echo "📡 [4/7] Installing gr-bladeRF (Source)..."
BLADERF_SRC_DIR="$SCRIPT_DIR/gr-bladeRF"

if [ ! -d "$BLADERF_SRC_DIR" ]; then
    echo "   Cloning into $BLADERF_SRC_DIR..."
    git clone https://github.com/Nuand/gr-bladeRF.git "$BLADERF_SRC_DIR"
fi

cd "$BLADERF_SRC_DIR"

# Checkout known good commit
KNOWN_GOOD_COMMIT="27de289"
echo "   Checking out stable commit $KNOWN_GOOD_COMMIT..."
git checkout "$KNOWN_GOOD_COMMIT"

# Build
mkdir -p build
cd build
cmake -DCMAKE_INSTALL_PREFIX=/usr ..
make -j$(nproc)
make install
ldconfig

# Fix ownership
chown -R "$ORIGINAL_USER:$ORIGINAL_USER" "$BLADERF_SRC_DIR"

# --- 5. INSTALL GR-AOA (YOUR CUSTOM MODULE) ---
echo "🎯 [5/7] Installing gr-aoa (Your Module)..."

# The gr-aoa repository is expected to be co-located with this script
# Navigate into the gr-aoa directory to build it.
AOA_SRC_DIR="$SCRIPT_DIR/gr-aoa"

if [ ! -d "$AOA_SRC_DIR" ]; then
    echo "❌ Error: gr-aoa directory not found at $AOA_SRC_DIR. Please ensure it's present."
    exit 1
fi

cd "$AOA_SRC_DIR"

# Build with Python Path Fixes (using in-source build as a workaround for path issues)
echo "   Configuring CMake with dynamic Python Path..."
PYTHON_SITEDIR=$(python3 -c "import site; print(site.getsitepackages()[0])")
cmake -DCMAKE_INSTALL_PREFIX=/usr \
      -DGR_PYTHON_DIR="$PYTHON_SITEDIR" \
      .

make -j$(nproc)
make install
ldconfig

# Fix ownership
chown -R "$ORIGINAL_USER:$ORIGINAL_USER" "$AOA_SRC_DIR"

# --- 6. USER PERMISSIONS ---
echo "👤 [6/7] Finalizing Permissions..."

# Add to plugdev (BladeRF)
if ! groups "$ORIGINAL_USER" | grep &>/dev/null '\bplugdev\b'; then
    usermod -aG plugdev "$ORIGINAL_USER"
    echo "   Added to 'plugdev' group."
fi

# Add to dialout (Arduino)
if ! groups "$ORIGINAL_USER" | grep &>/dev/null '\bdialout\b'; then
    usermod -aG dialout "$ORIGINAL_USER"
    echo "   Added to 'dialout' group."
fi

# --- 7. VERIFICATION ---
echo "✅ [7/7] Verifying Setup..."

# Verify Python Import
if python3 -c "from gnuradio import aoa; print('   AOA Module Import: SUCCESS')"; then
    echo "   Python environment is correct."
else
    echo "❌ ERROR: Python could not import 'aoa'. Check CMake output."
    exit 1
fi

echo "==================================================="
echo "🎉 SETUP COMPLETE!"
echo "   All source code is in: $SCRIPT_DIR"
echo "   1. Please RESTART YOUR TERMINAL (or Log Out/In) to apply permissions."
echo "   2. Ensure devices are attached via usbipd (Windows)."
echo "   3. Run 'volk_profile' if you haven't yet."
echo "==================================================="
