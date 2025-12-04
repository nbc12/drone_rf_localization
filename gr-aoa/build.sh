#!/bin/bash

# =================================================================
# AUTOMATED INSTALLER FOR GR-AOA (GNU Radio OOT Module)
# =================================================================
# Usage: sudo ./install_aoa.sh
#
# This script performs the following:
# 1. Installs system dependencies (GNU Radio, CMake, Python libs).
# 2. Configures USB/Serial permissions for the non-root user.
# 3. Clones the repository INTO THE CURRENT DIRECTORY.
# 4. Builds and Installs the module system-wide (fixing Python paths).
# =================================================================

# --- CONFIGURATION ---
# REPLACE THIS WITH YOUR GITHUB URL
REPO_URL="https://github.com/YOUR_USERNAME/gr-aoa.git"

# DETERMINE SCRIPT LOCATION
# This ensures we install alongside the script, even if run from elsewhere
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
INSTALL_DIR="$SCRIPT_DIR"

# --- SAFETY CHECKS ---
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Please run as root (use sudo)."
  exit 1
fi

if [ -z "$SUDO_USER" ]; then
  echo "❌ Error: Could not detect the actual user. Are you running in a root shell?"
  exit 1
fi

echo "==================================================="
echo "🚀 STARTING GR-AOA INSTALLATION"
echo "   Target User: $SUDO_USER"
echo "   Location:    $INSTALL_DIR"
echo "   Repo:        $REPO_URL"
echo "==================================================="

# 1. UPDATE AND INSTALL DEPENDENCIES
echo "📦 [1/6] Installing System Dependencies..."
apt-get update -qq
apt-get install -y \
    gnuradio-dev \
    cmake \
    build-essential \
    git \
    python3-serial \
    python3-numpy \
    python3-setuptools \
    linux-tools-virtual \
    hwdata

# 2. CONFIGURE PERMISSIONS (DIALOUT)
echo "🔑 [2/6] Configuring User Permissions..."
# Check if user is already in dialout
if groups "$SUDO_USER" | grep &>/dev/null '\bdialout\b'; then
    echo "   User $SUDO_USER is already in 'dialout'."
else
    echo "   Adding $SUDO_USER to 'dialout' group (Required for Arduino)..."
    usermod -aG dialout "$SUDO_USER"
    echo "   ⚠️  NOTE: You must LOG OUT and LOG IN for this to take effect!"
fi

# 3. CLONE REPOSITORY
echo "⬇️  [3/6] Cloning Repository..."
cd "$INSTALL_DIR"

# Extract repo name from URL (e.g., gr-aoa.git -> gr-aoa)
REPO_NAME=$(basename "$REPO_URL" .git)

# Clean up previous install if it exists
if [ -d "$REPO_NAME" ]; then
    echo "   Removing existing directory '$REPO_NAME'..."
    rm -rf "$REPO_NAME"
fi

git clone "$REPO_URL"
cd "$REPO_NAME"

# Fix ownership (since we are running as sudo, clone belongs to root by default)
# We give it back to the user who ran sudo
chown -R "$SUDO_USER":"$SUDO_USER" "$INSTALL_DIR/$REPO_NAME"

# 4. PREPARE BUILD DIRECTORY
echo "🔨 [4/6] Configuring Build..."
rm -rf build
mkdir build
cd build

# 5. CMAKE & INSTALL (The Critical Fixes)
# We force CMAKE_INSTALL_PREFIX to /usr for system-wide access
# We force GR_PYTHON_DIR to /usr/lib/python3/dist-packages to fix Import Errors
echo "🔧 [5/6] Compiling and Installing..."

cmake -DCMAKE_INSTALL_PREFIX=/usr \
      -DGR_PYTHON_DIR=/usr/lib/python3/dist-packages \
      ..

make -j$(nproc)
make install
ldconfig

# 6. VERIFICATION
echo "✅ [6/6] Verifying Installation..."
if python3 -c "from gnuradio import aoa; print('   Import Successful!')"; then
    echo "==================================================="
    echo "🎉 INSTALLATION COMPLETE SUCCESSFULY!"
    echo "   Location: $INSTALL_DIR/$REPO_NAME"
    echo "   You can now open GNU Radio Companion."
    echo "   Note: If you just added permissions, please restart WSL."
    echo "==================================================="
else
    echo "❌ INSTALLATION FAILED: Python could not import 'aoa'."
    exit 1
fi