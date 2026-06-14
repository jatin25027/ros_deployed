#!/bin/bash

echo "=================================="
echo "  ROS Project Runner - Setup"
echo "=================================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed!"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js version: $(node --version)"
echo "✅ npm version: $(npm --version)"
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ package.json not found!"
    echo "Please run this script from /home/jatin/ros_full/"
    exit 1
fi

echo "📦 Installing dependencies..."
npm install

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "=================================="
    echo "  To start the server:"
    echo "=================================="
    echo "npm start"
    echo ""
    echo "Then open http://localhost:3000 in your browser"
    echo ""
else
    echo "❌ Installation failed!"
    exit 1
fi
