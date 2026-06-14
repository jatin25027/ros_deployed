#!/bin/bash
# ROS 2 Humble installation script for Ubuntu 22.04 (Jammy)
# Run with: bash install_ros2_humble.sh

set -e
echo "============================================"
echo "  Installing ROS 2 Humble on Ubuntu 22.04  "
echo "============================================"

# Step 1: Set locale
echo "[1/7] Setting locale..."
sudo apt update && sudo apt install -y locales
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8

# Step 2: Enable universe repo
echo "[2/7] Enabling universe repository..."
sudo apt install -y software-properties-common
sudo add-apt-repository universe -y

# Step 3: Add ROS 2 GPG key
echo "[3/7] Adding ROS 2 GPG key..."
sudo apt update && sudo apt install -y curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg

# Step 4: Add ROS 2 repo
echo "[4/7] Adding ROS 2 repository..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Step 5: Update & install ROS 2 Humble (base)
echo "[5/7] Installing ROS 2 Humble base (this will take several minutes)..."
sudo apt update
sudo apt install -y ros-humble-ros-base python3-colcon-common-extensions

# Step 6: Install colcon
echo "[6/7] Installing colcon build tool..."
sudo apt install -y python3-colcon-common-extensions

# Step 7: Source setup
echo "[7/7] Setting up environment..."
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source /opt/ros/humble/setup.bash

echo ""
echo "============================================"
echo "  ROS 2 Humble installation COMPLETE!"
echo "  Run: source /opt/ros/humble/setup.bash"
echo "  Then restart the ROS Project Runner"
echo "============================================"
