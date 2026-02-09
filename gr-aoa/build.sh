#!/bin/bash

# =================================================================
# BUILD SCRIPT FOR GR-AOA
# =================================================================
# Usage: sudo ./build.sh
#
# This script builds and installs the CURRENT directory.
# It uses specific flags to ensure python modules are installed
# to the correct system path (/usr/lib/python3/dist-packages).
# =================================================================

# --- SAFETY CHECKS ---
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: Please run as root (use sudo)."
  exit 1
fi

# DETERMINE SCRIPT LOCATION
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "==================================================="
echo "🚀 STARTING GR-AOA BUILD"
echo "   Location: $SCRIPT_DIR"
echo "==================================================="

# 0. SYNC TIME (CRITICAL FOR WSL2)
echo "🕒 [0/5] Syncing clock with Windows host..."
hwclock -s

# 1. PREPARE BUILD DIRECTORY
echo "🔨 [1/4] Configuring Build Directory..."
rm -rf build
mkdir build
cd build

# 2. CMAKE
# We force CMAKE_INSTALL_PREFIX to /usr for system-wide access
# We force GR_PYTHON_DIR to /usr/lib/python3/dist-packages to fix Import Errors
echo "🔧 [2/4] Running CMake..."
cmake -DCMAKE_INSTALL_PREFIX=/usr \
      -DGR_PYTHON_DIR=/usr/lib/python3/dist-packages \
      ..

if [ $? -ne 0 ]; then
    echo "❌ CMake failed."
    exit 1
fi

# 3. COMPILE
echo "🧱 [3/4] Compiling..."
make -j$(nproc)

if [ $? -ne 0 ]; then
    echo "❌ Compilation failed."
    exit 1
fi

# 4. INSTALL
echo "💿 [4/4] Installing..."
make install
ldconfig

# 5. VERIFICATION
echo "🔍 [5/5] Verifying Installation..."
if python3 -c "from gnuradio import aoa; assert aoa.AOA_MAGIC == 987654321, 'Magic number mismatch'; print('   Import Successful & Magic Number Verified!')" 2>/dev/null; then
    echo "==================================================="
    echo "🎉 BUILD & INSTALL COMPLETE SUCCESSFULY!"
    echo "   You can now use the 'aoa' module in GNU Radio."
    echo "==================================================="
else
    echo "❌ ERROR: Installation finished, but verification failed."
    echo "   Either Python cannot import 'aoa', or the Magic Number does not match."
    echo "   Check your PYTHONPATH or ensure the new code was actually installed."
    exit 1
fi