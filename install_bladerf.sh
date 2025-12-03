#!/bin/bash
# A comprehensive script to install udev rules and build gr-bladeRF.
# This script checks out a specific commit known to be compatible
# with older libbladeRF versions to avoid compilation errors, and
# downloads the necessary bladeRF FPGA firmware to the user's home directory.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Prequsites check and dependency installation ---

# Check if the script is being run as root.
if [ "$(id -u)" -ne 0 ]; then
    echo "This script must be run with sudo."
    exit 1
fi

# --- Determine original user and home directory ---
# When running with sudo, $HOME points to /root. We use SUDO_USER to
# find the original user's home directory for the source code installation.
ORIGINAL_USER="${SUDO_USER:-$(whoami)}"
ORIGINAL_HOME=$(getent passwd "$ORIGINAL_USER" | cut -d: -f6)

if [ -z "$ORIGINAL_HOME" ]; then
    echo "Error: Could not determine home directory for user: $ORIGINAL_USER"
    exit 1
fi

echo "Script executing for user '$ORIGINAL_USER' with home directory: $ORIGINAL_HOME"
echo "---------------------------------------------------------"

echo "Updating package lists and installing core dependencies..."

# Update package lists
apt update

# Define all necessary build tools and libraries.
DEPS=(
    "git"
    "cmake"
    "build-essential"
    "gnuradio"
    "gnuradio-dev"
    "gr-osmosdr"
    "libbladerf-dev"
    "libbladerf2"
    "libgtk-3-dev"
    "wget"
)

# Install all dependencies in one command for efficiency.
apt install -y "${DEPS[@]}"

# --- Firmware Download ---

FIRMWARE_URL="https://www.nuand.com/fpga/v0.15.3/hostedxA4.rbf"
FIRMWARE_FILENAME=$(basename "$FIRMWARE_URL")
FIRMWARE_PATH="$ORIGINAL_HOME/$FIRMWARE_FILENAME"

echo "Attempting to download bladeRF FPGA firmware..."

if [ -f "$FIRMWARE_PATH" ]; then
    echo "Firmware file **$FIRMWARE_FILENAME already exists** in $ORIGINAL_HOME. Skipping download."
else
    echo "Downloading $FIRMWARE_FILENAME to $ORIGINAL_HOME..."
    # Use wget to download the file to the user's home directory
    # -P: specify directory prefix (user's home)
    # --no-verbose: reduces output noise
    wget --no-verbose -P "$ORIGINAL_HOME" "$FIRMWARE_URL"
    # Correct the ownership of the downloaded file
    chown "$ORIGINAL_USER:$ORIGINAL_USER" "$FIRMWARE_PATH"
    echo "Firmware download complete and ownership set."
fi


# --- Install gr-bladeRF from source ---

echo "Installing gr-bladeRF from source..."

# Use a specific directory for the build, based on the original user's home.
INSTALL_DIR="$ORIGINAL_HOME/src/gr-bladerf"

# Change to the original user's home directory first
cd "$ORIGINAL_HOME"

# Clone the repository if it doesn't already exist
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Cloning gr-bladeRF repository into $INSTALL_DIR..."
    git clone https://github.com/Nuand/gr-bladeRF.git "$INSTALL_DIR"
fi

# Change into the installation directory
cd "$INSTALL_DIR"

# --- Check out known-good commit ---
KNOWN_GOOD_COMMIT="27de289"
echo "Checking out known-good commit ($KNOWN_GOOD_COMMIT) to ensure compatibility..."
git checkout "$KNOWN_GOOD_COMMIT"

# Create and change into the build directory
if [ ! -d "build" ]; then
    mkdir build
fi
cd build

echo "Configuring the build with cmake..."
cmake ..

echo "Building gr-bladeRF with 4 parallel jobs..."
make -j4

echo "Installing gr-bladeRF..."
# This installs files globally (e.g., in /usr/local/lib/python3/dist-packages)
make install

# --- Fix ownership of the source directory ---
echo "Setting ownership of $INSTALL_DIR back to $ORIGINAL_USER..."
chown -R "$ORIGINAL_USER:$ORIGINAL_USER" "$INSTALL_DIR"

# Update the library cache
echo "Updating shared library cache..."
ldconfig

# --- Install udev rules ---

RULES_FILE="/etc/udev/rules.d/88-nuand.rules"

echo "Checking for existing bladeRF udev rules file: $RULES_FILE"

if [ -f "$RULES_FILE" ]; then
    # If the file exists, notify the user and skip creation/modification
    echo "Udev rules file **$RULES_FILE already exists**. Skipping creation to avoid overwrite."
    echo "If you need to update the rules, please do so manually."
else
    # If the file does not exist, create it and apply the rules
    echo "Installing $RULES_FILE for bladeRF devices..."

    # Create the rules file with the correct content.
    # 'tee' is used to write to a root-owned file.
    tee "$RULES_FILE" > /dev/null <<EOF
# bladeRF 1.0 (fx3)
ATTRS{idVendor}=="2cf0", ATTRS{idProduct}=="5250", MODE="0660", GROUP="plugdev"
# bladeRF 2.0 micro (fx3)
ATTRS{idVendor}=="2cf0", ATTRS{idProduct}=="525a", MODE="0660", GROUP="plugdev"
EOF

    # Set the correct file permissions for the rules file.
    chmod 644 "$RULES_FILE"
    echo "Permissions set for $RULES_FILE."

    # Reload the udev rules.
    echo "Reloading udev rules..."
    udevadm control --reload-rules

    # Trigger udev to apply the new rules to currently connected devices.
    echo "Triggering udev rules to apply to existing devices..."
    udevadm trigger

fi

echo "bladeRF udev rules and gr-bladeRF installation complete."
echo "Please re-plug your bladeRF device for the new rules to take full effect."

exit 0
